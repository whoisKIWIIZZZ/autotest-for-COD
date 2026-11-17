import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from coe_to_hex import load_coe
from sim.cases import (CASES, DEFAULT_CASE_IDS, MAX_RECORDED_FRAMES, inspect_case_frames,
                       select_cases, write_monitor_header)
from sim.diagnostics import diagnose_failure, save_unavailable


PERIPHERALS = ("MIO_BUS", "SSeg7", "Multi_8CH32", "SPIO", "dm_controller")
NUMERIC_FUNCTIONS = frozenset((
    "signed unsigned clog2 bits size dimensions unpacked_dimensions left right low high increment "
    "countones countbits onehot onehot0 isunknown rtoi itor realtobits bitstoreal "
    "shortrealtobits bitstoshortreal ceil floor ln log10 exp sqrt pow sin cos tan asin acos atan "
    "atan2 hypot sinh cosh tanh asinh acosh atanh"
).split())
LEXEMES = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\[\s\S]|[^"\\])*"')


def build_jobs() -> str:
    override = os.environ.get("SCPU_BUILD_JOBS", "")
    if override.isdigit() and int(override) >= 1:
        return override
    # GCC 8 的并行构建会在预编译头尚未完成时编译对象，默认串行。
    return "1"


class InvalidSubmission(ValueError):
    pass


def validate_rtl(files, reserved):
    # 先检查原文，再屏蔽注释和字符串；不依赖可被预处理宏绕过的任务黑名单。
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError as exc:
            raise InvalidSubmission(f"{path.name} 不是 UTF-8 文本") from exc
        if "\x00" in text:
            raise InvalidSubmission(f"{path.name} 含空字节")
        for match in LEXEMES.finditer(text):
            token = match.group()
            if token.startswith(("//", "/*")):
                comment = token[2:-2] if token.startswith("/*") else token[2:]
                if re.match(r"\s*verilator\b", comment, re.I) and not re.fullmatch(
                        r"\s*verilator\s+(?:lint_off|lint_on|coverage_off|coverage_on)(?:\s+[A-Za-z0-9_ -]+)?\s*",
                        comment, re.I):
                    raise InvalidSubmission(f"{path.name} 含不安全的 Verilator 元注释")
        plain = LEXEMES.sub(lambda match: " " * len(match.group()), text)
        # 防止反斜杠换行拼接关键字；普通行续接宏仍可使用。
        joined = re.sub(r"\\\r?\n", "", plain)
        if re.search(r"\b(?:force|release|bind)\b|\bjudge_top\b", joined):
            raise InvalidSubmission(f"{path.name} 含越界层次操作或 force/release/bind")
        if re.search(r'\b(?:import|export)\s*"\s*DPI', text, re.I):
            raise InvalidSubmission(f"{path.name} 不允许 DPI 或 C/C++ 接口")
        for match in re.finditer(r"(?<![A-Za-z0-9_$])\$(?:[A-Za-z_][A-Za-z0-9_$]*)?", joined):
            if match.group()[1:] not in NUMERIC_FUNCTIONS:
                raise InvalidSubmission(f"{path.name} 不允许系统任务/函数 {match.group()}")
        for name in re.findall(r"\bmodule\s+(?:automatic\s+|static\s+)?([A-Za-z_][A-Za-z0-9_$]*)", joined):
            if name in reserved:
                raise InvalidSubmission(f"{path.name} 不得替换评测器模块 {name}")
        # include 只能指向本次提交中的文本依赖，不能读主机文件或评测器实现。
        uncommented = re.sub(r"//[^\n]*|/\*[\s\S]*?\*/", "", text)
        for line in uncommented.splitlines():
            if re.search(r"`\s*include\b", line):
                match = re.fullmatch(r'\s*`include\s+"([^"\\]+)"\s*', line)
                if match is None or match.group(1) not in {item.name for item in files}:
                    raise InvalidSubmission(f"{path.name} 的 include 必须是本次提交文件的直接文件名")
        if re.search(r"`\s*(?:protect|protected|pragma|uselib|begin_keywords|end_keywords)\b", joined):
            raise InvalidSubmission(f"{path.name} 含不支持的编译器控制指令")


ENVIRONMENT_COMPILER_FAILURES = (
    "had text segment at different address",
    "PCH files were found, but they were invalid",
)


def compiler_environment_failure(run_dir):
    # 预编译头与本机 ASLR 冲突属于评测环境问题，不应记为学生编译错误。
    path = run_dir / "logs" / "run.log"
    try:
        with path.open("rb") as incoming:
            incoming.seek(max(0, path.stat().st_size - 1_000_000))
            text = incoming.read().decode("utf-8", "replace")
    except OSError:
        return False
    return any(marker in text for marker in ENVIRONMENT_COMPILER_FAILURES)


def write_json(path, data):
    temporary = path.with_name(path.name + ".new")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def snapshot(run_dir, kind, suite):
    submission = run_dir / "submission"
    if submission.is_symlink() or not submission.is_dir():
        raise InvalidSubmission("缺少真实 submission 目录")
    uploads = sorted(submission.iterdir())
    allowed = {".v", ".sv", ".vh", ".svh"} if kind == "rtl" else {".edf", ".edif"}
    if not uploads or len(uploads) > 64:
        raise InvalidSubmission("必须提交 1 至 64 个文件")
    for path in uploads:
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in allowed:
            raise InvalidSubmission(f"非法提交文件：{path.name}")
        if (path.name.strip() != path.name or "\\" in path.name
                or len(path.name.encode("utf-8")) > 240
                or any(ord(character) < 32 for character in path.name)):
            raise InvalidSubmission(f"文件名不能包含目录或控制字符：{path.name}")
    if sum(path.stat().st_size for path in uploads) > 32 * 1024 * 1024:
        raise InvalidSubmission("提交文件总大小超过 32 MiB")
    if kind == "edf" and len(uploads) != 1:
        raise InvalidSubmission("EDF 调试仅接受一个自包含 SCPU 网表")
    if kind == "rtl" and not any(path.suffix.lower() in {".v", ".sv"} for path in uploads):
        raise InvalidSubmission("RTL 提交至少需要一个 .v 或 .sv 编译单元")
    work = run_dir / "work"
    work.mkdir(exist_ok=False)
    sources = work / "src"
    sources.mkdir()
    runtime = work / "runtime"
    runtime.mkdir()
    copied_uploads = work / "submission"
    copied_uploads.mkdir()
    for path in uploads:
        shutil.copy2(path, copied_uploads / path.name)
    copies = [ROOT / "main.v", ROOT / "sim/cases.py",
              ROOT / "IO/clk_div.v", ROOT / "IO/Enter.v", ROOT / "IO/Counter_3_IO.v",
              ROOT / "sim/memory.v", ROOT / "sim/judge_top.v", ROOT / "sim/run_testac.cpp",
              ROOT / "sim/trace_stream.h", ROOT / "sim/trace_compare.py", ROOT / "sim/diagnostics.py",
              ROOT / "sim/animation.py", ROOT / "sim/evaluate.py", ROOT / "sim/convert_edif.py",
              ROOT / "sim/coe_to_hex.py", ROOT / "sim/vendor/xilinx_cells_sim.v"]
    for path in copies:
        shutil.copy2(path, sources / path.name)
    edfs = work / "edf"
    edfs.mkdir()
    for name in (*PERIPHERALS, "SCPU"):
        shutil.copy2(ROOT / "edf_file" / f"{name}.edf", edfs / f"{name}.edf")
    programs = sources / "programs"
    programs.mkdir()
    for name in dict.fromkeys(spec.program for spec in suite):
        for extension in ("S", "coe"):
            shutil.copy2(ROOT / "programs" / f"{name}.{extension}", programs / f"{name}.{extension}")
    for spec in suite:
        words = load_coe(programs / f"{spec.program}.coe")
        if len(words) > 1024:
            raise RuntimeError(f"{spec.id} 超出 ROM 容量")
        case_runtime = runtime / spec.id
        case_runtime.mkdir()
        (case_runtime / "program.hex").write_text("".join(
            f"{word:08x}\n" for word in words + [0x13] * (1024 - len(words))), encoding="ascii")
        (case_runtime / "frames.jsonl").touch()
    write_json(work / "suite.json", {"suite": [spec.id for spec in suite]})
    write_monitor_header(sources / "monitor_config.h", suite)
    return work, sources, runtime, sorted(copied_uploads.iterdir())


def prepare_sources(work, sources, uploads, kind):
    # 沿用现有 SpyDrNet 展平/总线转换 API，不引入第二套网表解释器。
    from convert_edif import convert
    netlists = work / "netlist"
    netlists.mkdir()
    vendor = (sources / "xilinx_cells_sim.v").read_text()
    primitives = set(re.findall(r"\bmodule\s+([A-Za-z_][A-Za-z0-9_$]*)", vendor))
    reserved = primitives | set(PERIPHERALS) | {"main", "ROM", "RAM", "Enter", "clk_div", "Counter_x", "judge_top"}
    if kind == "rtl":
        validate_rtl(uploads, reserved)
        cpu_sources = [path for path in uploads if path.suffix.lower() in {".v", ".sv"}]
    else:
        # 输入端口/库声明必须来自完整网表，不能以另一个顶层替换 SCPU。
        from convert_edif import sdn
        try:
            netlist = sdn.parse(str(uploads[0]))
            if netlist.top_instance.reference.name != "SCPU":
                raise InvalidSubmission("EDF 顶层必须为 SCPU")
            for library in netlist.libraries:
                for definition in library.definitions:
                    if library.name == "hdi_primitives" and definition.name not in primitives:
                        raise InvalidSubmission(f"EDF 含不支持的原语 {definition.name}")
            del netlist
            convert(uploads[0], netlists / "SCPU.v")
            validate_rtl([netlists / "SCPU.v"], reserved)
        except (Exception, SystemExit) as exc:
            raise InvalidSubmission(f"SCPU EDF 无法安全转换：{exc}") from exc
        cpu_sources = [netlists / "SCPU.v"]
    for name in PERIPHERALS:
        convert(work / "edf" / f"{name}.edf", netlists / f"{name}.v")
    # 可信编译单元先于提交源，提交宏不得重写板级实现或监测探针。
    return ([sources / "xilinx_cells_sim.v"] +
            [netlists / f"{name}.v" for name in PERIPHERALS] +
            [sources / name for name in ("clk_div.v", "Enter.v", "Counter_3_IO.v", "memory.v", "main.v", "judge_top.v")] +
            cpu_sources), reserved


def read_frames(runtime):
    frames = []
    path = runtime / "frames.jsonl"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if len(frames) >= MAX_RECORDED_FRAMES:
                raise ValueError("显示帧超出监测器上限")
            frames.append(json.loads(line))
    return frames


def case_placeholder(spec):
    return {**spec.public(), "status": "queued", "summary": "等待执行", "cycles": 0,
            "duration_seconds": 0, "frames": 0, "checks": [], "native": None, "loop": None}


def run_case(spec, binary, runtime, run_dir):
    from execution import ExecutionError, ExecutionTimeout, run_command
    started = time.monotonic()
    outcome = case_placeholder(spec)
    outcome.update(status="judge_error", summary="用例未完成")
    try:
        code = run_command([str(binary), "--case", spec.id], cwd=runtime,
                           run_dir=run_dir, phase="simulate", timeout=5400)
        if code == 2:
            outcome.update(summary="原生监测器无法读取配置或写入证据文件")
        elif code != 0:
            outcome.update(status="wrong_answer", summary=f"仿真异常退出（退出码 {code}）")
        else:
            native = json.loads((runtime / "monitor_result.json").read_text())
            if native["case_id"] != spec.id or native["status"] not in {"accepted", "wrong_answer", "time_limit"}:
                raise ValueError("原生监测结果的用例或状态非法")
            frames = read_frames(runtime)
            if native["frames"] != len(frames):
                raise ValueError("原生监测帧数与实际证据文件不符")
            passed, checks, loop = inspect_case_frames(spec, frames)
            status = native["status"]
            if status == "accepted" and not passed:
                status = "wrong_answer"
            summaries = {
                "failure_pc": "程序进入 0x218 失败循环", "reset_pc": "复位后 PC 不为零",
                "invalid_pc": "PC 未对齐或超出指令 ROM", "stuck_pc": "PC 长时间停滞",
                "display_sequence": "实际显示顺序不符合完整动画程序",
                "selftest_marker": "启动自检内存标记错误", "cycle_limit": "超过该程序 CPU 周期上限",
                "display_progress_timeout": "显示长期没有进展",
                "unsolicited_display_change": "显示寄存器发生非预期变化",
                "unexpected_finish": "仿真被提前终止", "failure_display": "程序自检失败，数码管显示 FAIL",
                "display_frame_limit": "显示帧数超过监测上限",
            }
            success = ("已观测完整 AC 动画循环" if spec.full_animation else
                       f"已观测完整 AC：0x{spec.success_word:08x}" if spec.id == "testac-simple" else
                       "程序自检通过，数码管显示 PASS")
            outcome.update(status=status, summary=success if status == "accepted" else
                           summaries.get(native["reason"], "未观测到有效的成功显示证据"),
                           native=native, cycles=native["cycles"], checks=checks, loop=loop)
    except ExecutionTimeout as exc:
        outcome.update(status="time_limit", summary=f"仿真超时：{exc}")
    except ExecutionError as exc:
        outcome.update(status="judge_error", summary=f"评测环境错误：{exc}")
    except Exception as exc:
        traceback.print_exc()
        outcome.update(status="judge_error", summary=f"用例证据读取失败：{exc}")
    finally:
        try:
            frames = read_frames(runtime)
            outcome["frames"] = len(frames)
            if frames:
                outcome["cycles"] = max(outcome["cycles"], frames[-1]["cycle"])
            if not outcome["checks"]:
                _, outcome["checks"], _ = inspect_case_frames(spec, frames)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            outcome.update(status="judge_error", summary=f"显示证据读取失败：{exc}")
        outcome["duration_seconds"] = round(time.monotonic() - started, 6)
        write_json(runtime / "result.json", outcome)
    return outcome


def compile_submission(work, sources, uploads, kind, run_dir):
    from execution import ExecutionError, run_command
    units, reserved = prepare_sources(work, sources, uploads, kind)
    verilator = shutil.which("verilator")
    if verilator is None:
        raise ExecutionError("未安装 Verilator")
    if kind == "rtl":
        expanded = sources / "submission_expanded.sv"
        cpu_units = [path for path in uploads if path.suffix.lower() in {".v", ".sv"}]
        preprocessor = [verilator, "-E", "-P", "-I" + str(work / "submission")] + [str(path) for path in cpu_units]
        code = run_command(["/bin/sh", "-c", "exec " + shlex.join(preprocessor) + " > " + shlex.quote(str(expanded))],
                           cwd=work, run_dir=run_dir, phase="compile", timeout=120)
        if code != 0:
            raise InvalidSubmission(f"RTL 预处理失败（退出码 {code}），请查看编译日志")
        validate_rtl([expanded], reserved)
        units = [path for path in units if path not in cpu_units] + [expanded]
    command = [verilator, "--cc", "--exe", "--build", "-j", build_jobs(), "--no-timing",
               "--timescale-override", "1ns/1ps", "--top-module", "judge_top", "--prefix", "Vjudge_top", "--Mdir", str(work / "build"),
               "-O3", "-CFLAGS", "-O3 -march=native", "-Wno-fatal", "-Werror-MODDUP", "--output-split", "12000",
               "--output-split-cfuncs", "1000", "-I" + str(work / "submission"),
               "-I" + str(sources)] + [str(path) for path in units] + [str(sources / "run_testac.cpp")]
    code = run_command(command, cwd=work, run_dir=run_dir, phase="compile", timeout=1200)
    return code


def evaluate(run_dir, kind, case_ids=DEFAULT_CASE_IDS):
    from execution import ExecutionError, ExecutionTimeout
    suite = select_cases(case_ids)
    started = time.monotonic()
    result = {"status": "judge_error", "score": None, "summary": "评测器未完成",
              "cycles": 0, "duration_seconds": 0, "checks": [], "loop": None,
              "suite": [spec.id for spec in suite], "cases": [case_placeholder(spec) for spec in suite]}
    runtime = None
    try:
        for name in ("TMPDIR", "TMP", "TEMP"):
            os.environ[name] = str(run_dir / "tmp")
        (run_dir / "tmp").mkdir(exist_ok=True)
        work, sources, runtime, uploads = snapshot(run_dir, kind, suite)
        write_json(runtime / "progress.json", {"cases": result["cases"], "active_case": None})
        code = compile_submission(work, sources, uploads, kind, run_dir)
        result["checks"].append({"name": "Verilator 编译", "passed": code == 0, "detail": f"退出码 {code}"})
        if code != 0:
            if compiler_environment_failure(run_dir):
                result.update(status="judge_error", summary="评测环境编译器预编译头故障，本次不计分。")
            else:
                result.update(status="compile_error", summary="SCPU 编译失败，请查看完整编译日志")
        else:
            binary = work / "build" / "Vjudge_top"
            for index, spec in enumerate(suite):
                print(f"开始用例 {index + 1}/{len(suite)}：{spec.id}（{spec.label}）", flush=True)
                result["cases"][index].update(status="running", summary="正在执行真实 CPU 程序")
                write_json(runtime / "progress.json", {"cases": result["cases"], "active_case": spec.id})
                outcome = run_case(spec, binary, runtime / spec.id, run_dir)
                if outcome["status"] in {"wrong_answer", "time_limit"}:
                    result["cases"][index] = {**outcome, "summary": outcome["summary"] + "；正在复放定位首差"}
                    write_json(runtime / "progress.json", {"cases": result["cases"], "active_case": spec.id})
                    outcome["first_diff"] = diagnose_failure(
                        spec, binary, runtime / spec.id, run_dir, work, sources, outcome)
                    if outcome["first_diff"]["status"] == "different":
                        outcome["summary"] += f"；首差周期 {outcome['first_diff']['first_cycle']}"
                    write_json(runtime / spec.id / "result.json", outcome)
                result["cases"][index] = outcome
                write_json(runtime / "progress.json", {"cases": result["cases"], "active_case": None})
                print(f"用例 {spec.id}：{outcome['status']}，{outcome['summary']}", flush=True)
                if outcome["status"] == "judge_error":
                    break
            statuses = {case["status"] for case in result["cases"]}
            passed = sum(case["status"] == "accepted" for case in result["cases"])
            if statuses == {"accepted"}:
                result.update(status="accepted", summary=f"{passed}/{len(suite)} 个程序全部通过")
            elif statuses & {"judge_error", "queued"}:
                result.update(status="judge_error", summary="评测环境故障，部分程序未能完成")
            else:
                status = "wrong_answer" if "wrong_answer" in statuses else "time_limit"
                result.update(status=status, summary=f"{passed}/{len(suite)} 个程序通过，请查看逐例结果")
    except InvalidSubmission as exc:
        result.update(status="compile_error", summary=f"提交源文件无效：{exc}")
        result["checks"].append({"name": "硬件源安全检查", "passed": False, "detail": str(exc)})
    except ExecutionTimeout as exc:
        result.update(status="compile_error", summary=f"编译超时：{exc}")
    except ExecutionError as exc:
        result.update(status="judge_error", summary=f"评测环境错误：{exc}")
    except Exception as exc:
        traceback.print_exc()
        result.update(status="judge_error", summary=f"评测器异常：{exc}")
    finally:
        for outcome in result["cases"]:
            if outcome["status"] in {"queued", "running"}:
                outcome.update(status="compile_error" if result["status"] == "compile_error" else "interrupted",
                               summary="未执行：" + result["summary"])
            if outcome["status"] != "accepted" and "first_diff" not in outcome:
                if runtime is None:
                    runtime = run_dir / "work/runtime"
                outcome["first_diff"] = save_unavailable(
                    runtime / outcome["id"], "该用例未完成硬件执行：" + outcome["summary"])
                write_json(runtime / outcome["id"] / "result.json", outcome)
            for check in outcome["checks"]:
                result["checks"].append({**check, "name": f"{outcome['label']} · {check['name']}"})
        result["first_diff"] = next((outcome["first_diff"] for outcome in result["cases"]
                                     if "first_diff" in outcome), None)
        result["cycles"] = sum(outcome["cycles"] for outcome in result["cases"])
        result["loop"] = next((outcome["loop"] for outcome in result["cases"] if outcome["loop"]), None)
        result["score"] = 100 if result["status"] == "accepted" else 0 if result["status"] in {
            "compile_error", "wrong_answer", "time_limit"} else None
        result["duration_seconds"] = round(time.monotonic() - started, 6)
        if runtime is not None:
            write_json(runtime / "progress.json", {"cases": result["cases"], "active_case": None})
        write_json(run_dir / "result.json", result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description="真实执行 SCPU 的快速幂、递归 fib 和数码管 AC 程序")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--kind", choices=("rtl", "edf"), required=True)
    parser.add_argument("--cases", nargs="+", choices=tuple(CASES), default=DEFAULT_CASE_IDS)
    args = parser.parse_args()
    try:
        select_cases(args.cases)
    except ValueError as exc:
        parser.error(str(exc))
    run_dir = args.run_dir.resolve()
    if not args.run_dir.is_absolute() or not run_dir.is_relative_to(ROOT) or run_dir == ROOT:
        parser.error("run-dir 必须是项目目录内的绝对路径")
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        return evaluate(run_dir, args.kind, args.cases)
    except Exception as exc:
        traceback.print_exc()
        write_json(run_dir / "result.json", {
            "status": "judge_error", "score": None, "summary": f"评测初始化失败：{exc}",
            "cycles": 0, "duration_seconds": 0, "checks": [], "loop": None,
            "suite": list(args.cases), "cases": []})
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
