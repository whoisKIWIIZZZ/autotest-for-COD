import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import threading
import traceback

import psutil

from execution import command_environment
from storage import MAX_FILES, MAX_TOTAL_BYTES, ROOT, RunStore
from sim.cases import CASES, DEFAULT_CASE_IDS, select_cases


TOTAL_TIMEOUT = 7200
RTL_SUFFIXES = {".v", ".sv", ".vh", ".svh"}


def validate_files(kind: str, filenames: list[str]) -> None:
    if kind not in {"rtl", "edf"}:
        raise ValueError("请选择 RTL 或 EDF 调试提交。")
    if not 1 <= len(filenames) <= MAX_FILES:
        raise ValueError(f"请选择 1–{MAX_FILES} 个 SCPU 文件。")
    if len({name.casefold() for name in filenames}) != len(filenames):
        raise ValueError("文件名重复，请为每个文件使用独立名称。")
    for name in filenames:
        if (not name or name.strip() != name or Path(name).name != name or "\\" in name
                or len(name.encode("utf-8")) > 240 or any(ord(character) < 32 for character in name)):
            raise ValueError("文件名须为不包含目录和控制字符的普通文件名。")
        allowed = RTL_SUFFIXES if kind == "rtl" else {".edf", ".edif"}
        if Path(name).suffix.lower() not in allowed:
            raise ValueError("RTL 支持 .v/.sv/.vh/.svh；EDF 调试支持 .edf/.edif。")
    if kind == "edf" and len(filenames) != 1:
        raise ValueError("EDF 调试请提交一个包含 SCPU 的完整网表。")
    if kind == "rtl" and not any(Path(name).suffix.lower() in {".v", ".sv"} for name in filenames):
        raise ValueError("RTL 提交需要至少一个 .v 或 .sv 编译文件。")


def terminate_tree(process: subprocess.Popen) -> None:
    try:
        parent = psutil.Process(process.pid)
        children = parent.children(recursive=True)
    except psutil.NoSuchProcess:
        return
    processes = [*reversed(children), parent]
    for item in processes:
        try:
            item.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(processes, timeout=3)
    for item in alive:
        try:
            item.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(alive, timeout=3)


class RunManager:
    def __init__(self, store: RunStore):
        self.store = store
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scpu-grader")
        self.stopping = threading.Event()
        self.lock = threading.Lock()
        self.active: dict[int, subprocess.Popen] = {}

    def submit(self, run_id: int) -> None:
        self.worker.submit(self.execute, run_id)

    def execute(self, run_id: int) -> dict | None:
        row = self.store.get(run_id)
        if row is None or row["state"] != "queued":
            return None
        if self.stopping.is_set():
            self.store.finish(run_id, {"status": "interrupted", "summary": "服务关闭，排队运行已中断。", "checks": []})
            return self.store.get(run_id)
        if not self.store.start(run_id):
            return None
        directory = Path(row["directory"])
        result = None
        timed_out = False
        process = None
        log_path = directory / "logs" / "run.log"
        try:
            with log_path.open("ab", buffering=0) as log:
                command = [sys.executable, "-u", str(ROOT / "sim" / "evaluate.py"),
                           "--run-dir", str(directory), "--kind", row["kind"], "--cases",
                           *json.loads((directory / "submission.json").read_text()).get("suite", DEFAULT_CASE_IDS)]
                log.write(("开始评测：" + json.dumps(command, ensure_ascii=False) + "\n").encode("utf-8"))
                process = subprocess.Popen(command, cwd=directory, env=command_environment(directory),
                                           stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                           start_new_session=True)
                with self.lock:
                    self.active[run_id] = process
                    if self.stopping.is_set():
                        terminate_tree(process)
                try:
                    returncode = process.wait(timeout=TOTAL_TIMEOUT)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    terminate_tree(process)
                    returncode = process.wait()
                result_path = directory / "result.json"
                if result_path.is_file():
                    result = json.loads(result_path.read_text(encoding="utf-8"))
                if timed_out:
                    result = {"status": "time_limit", "summary": "评测超过运行时间上限，部分程序未完成。", "checks": []}
                elif returncode != 0 or not isinstance(result, dict):
                    result = {"status": "judge_error", "summary": f"评测器异常退出（{returncode}），请查看完整日志。", "checks": []}
        except Exception:
            with log_path.open("a", encoding="utf-8") as log:
                log.write(traceback.format_exc())
            result = {"status": "judge_error", "summary": "评测执行异常，日志和已生成文件已保留。", "checks": []}
        finally:
            with self.lock:
                self.active.pop(run_id, None)
            if process is not None and process.poll() is None:
                terminate_tree(process)
        if self.stopping.is_set():
            result = {"status": "interrupted", "summary": "服务关闭，本次评测已中断；已有文件已保留。", "checks": []}
        self.store.finish(run_id, result)
        return self.store.get(run_id)

    def close(self) -> None:
        self.stopping.set()
        with self.lock:
            active = list(self.active.values())
        for process in active:
            terminate_tree(process)
        self.worker.shutdown(wait=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="提交 SCPU 文件并保留完整评测运行记录")
    parser.add_argument("--kind", choices=("rtl", "edf"), required=True)
    parser.add_argument("--student-id", default="local")
    parser.add_argument("--student-name", default="本机评测")
    parser.add_argument("--cases", nargs="+", choices=tuple(CASES), default=DEFAULT_CASE_IDS)
    parser.add_argument("files", type=Path, nargs="+")
    args = parser.parse_args()
    try:
        select_cases(args.cases)
        validate_files(args.kind, [path.name for path in args.files])
        if any(not path.is_file() or path.is_symlink() for path in args.files):
            raise ValueError("提交路径必须为实际文件。")
        if sum(path.stat().st_size for path in args.files) > MAX_TOTAL_BYTES:
            raise ValueError("提交文件合计不得超过 32 MiB。")
        student_id, student_name = args.student_id.strip(), args.student_name.strip()
        if not student_id or not student_name or len(student_id) > 64 or len(student_name) > 64:
            raise ValueError("学号和姓名须为 1–64 个字符。")
    except ValueError as error:
        parser.error(str(error))
    store = RunStore()
    store.initialize()
    row = store.create(student_id=student_id, student_name=student_name,
                       kind=args.kind, owner_digest=None,
                       files=[(path.name, path.resolve()) for path in args.files], case_ids=args.cases)
    print(f"run={row['id']} directory={row['directory']}", flush=True)
    manager = RunManager(store)
    try:
        if row["state"] == "queued":
            manager.execute(row["id"])
        finished = store.get(row["id"])
        print(json.dumps(store.view(finished), ensure_ascii=False, indent=2))
    except KeyboardInterrupt:
        manager.close()
        current = store.get(row["id"])
        if current["state"] != "finished":
            store.finish(row["id"], {"status": "interrupted", "summary": "命令行评测已中断。", "checks": []})
        return 130
    finally:
        manager.close()
    return 0 if finished["status"] == "accepted" else 2 if finished["score"] is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
