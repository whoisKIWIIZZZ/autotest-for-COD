import json
import math
import os
from pathlib import Path
import resource
import shlex
import shutil
import signal
import subprocess
import sys
import threading


class ExecutionError(RuntimeError):
    pass


class ExecutionTimeout(ExecutionError):
    pass


LINUX_READONLY = ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/lib32", "/etc", "/opt")


def command_environment(run_dir: Path) -> dict[str, str]:
    temporary = run_dir / "tmp"
    home = temporary / "home"
    cache = temporary / "clang-cache"
    for directory in (temporary, home, cache):
        directory.mkdir(parents=True, exist_ok=True)
    environment = {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": str(home),
        "TMPDIR": str(temporary),
        "TMP": str(temporary),
        "TEMP": str(temporary),
        "CLANG_MODULE_CACHE_PATH": str(cache),
        "XDG_CACHE_HOME": str(temporary / "cache"),
        "LC_ALL": "C",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    if "SCPU_BUILD_JOBS" in os.environ:
        environment["SCPU_BUILD_JOBS"] = os.environ["SCPU_BUILD_JOBS"]
    return environment


def sandbox_environment() -> dict[str, str]:
    # Linux 下父进程直接以最小环境启动 bwrap，不继承宿主的临时目录等设置。
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/tmp/home",
        "TMPDIR": "/tmp", "TMP": "/tmp", "TEMP": "/tmp",
        "CLANG_MODULE_CACHE_PATH": "/tmp/clang-cache",
        "XDG_CACHE_HOME": "/tmp/cache",
        "LC_ALL": "C", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
    }


def _darwin_profile(run_dir: Path, phase: str, executable: Path) -> str:
    readable = [
        run_dir,
        Path("/System"), Path("/Library"), Path("/usr"),
        Path("/opt/homebrew"), Path("/Applications"),
        Path("/private/etc"), Path("/private/var/db/timezone"), Path("/private/preboot"),
    ]
    writable = [run_dir / "tmp", run_dir / "work"] if phase == "compile" else [
        run_dir / "tmp", run_dir / "work" / "runtime",
    ]
    read_rules = '(literal "/") ' + " ".join(f"(subpath {json.dumps(str(path))})" for path in readable)
    write_rules = " ".join(f"(subpath {json.dumps(str(path))})" for path in writable)
    # 保留 Darwin 系统调用环境，通过目录、网络和执行权限限制学生进程。
    rules = [
        "(version 1)", "(allow default)", "(deny network*)",
        f"(deny file-read-data (require-not (require-any {read_rules} "
        '(literal "/dev/null") (literal "/dev/random") (literal "/dev/urandom"))))',
        f"(deny file-map-executable (require-not (require-any {read_rules})))",
        f"(deny file-write* (require-not (require-any {write_rules} (literal \"/dev/null\") "
        f"(literal {json.dumps(str(run_dir / 'logs' / 'run.log'))}))))",
    ]
    if phase == "simulate":
        rules.extend([
            "(deny process-fork)",
            f"(deny process-exec (require-not (literal {json.dumps(str(executable))})))",
        ])
    return "\n".join([*rules, ""])


def _translate(path: str, run_dir: Path) -> str:
    return path.replace(str(run_dir), "/run")


def _sandbox_path(host: Path, run_dir: Path) -> str:
    relative = host.resolve().relative_to(run_dir)
    return "/run" + (f"/{relative.as_posix()}" if relative.parts else "")


def _linux_command(command: list[str], run_dir: Path, cwd: Path, phase: str) -> list[str]:
    bubblewrap = shutil.which("bwrap")
    if bubblewrap is None:
        raise ExecutionError("缺少 bubblewrap（bwrap），无法隔离评测进程。")
    arguments = [
        bubblewrap, "--die-with-parent", "--new-session", "--unshare-all",
        "--proc", "/proc", "--dev", "/dev",
    ]
    for path in LINUX_READONLY:
        if Path(path).exists():
            arguments += ["--ro-bind", path, path]
    # 运行目录整体只读，只有明确的产物目录可写；网络在独立命名空间中关闭。
    arguments += ["--ro-bind", str(run_dir), "/run"]
    arguments += ["--bind", str(run_dir / "tmp"), "/run/tmp"]
    arguments += ["--bind", str(run_dir / "tmp"), "/tmp"]
    if phase == "compile":
        arguments += ["--bind", str(run_dir / "work"), "/run/work"]
    else:
        arguments += ["--bind", str(run_dir / "work" / "runtime"), "/run/work/runtime"]
    for key, value in {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/tmp/home",
        "TMPDIR": "/tmp", "TMP": "/tmp", "TEMP": "/tmp",
        "CLANG_MODULE_CACHE_PATH": "/tmp/clang-cache",
        "XDG_CACHE_HOME": "/tmp/cache",
        "LC_ALL": "C", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
    }.items():
        arguments += ["--setenv", key, value]
    arguments += ["--chdir", _sandbox_path(cwd, run_dir)]
    arguments += [_translate(argument, run_dir) for argument in command]
    return arguments


def _wrap_command(command: list[str], run_dir: Path, cwd: Path,
                  phase: str) -> tuple[list[str], Path]:
    executable = Path(command[0])
    if sys.platform == "darwin":
        profile = run_dir / "policies" / f"{phase}.sb"
        profile.parent.mkdir(exist_ok=True)
        profile.write_text(_darwin_profile(run_dir, phase, executable), encoding="utf-8")
        sandbox = shutil.which("sandbox-exec")
        if sandbox is None:
            raise ExecutionError("缺少 sandbox-exec，无法隔离评测进程。")
        return [sandbox, "-f", str(profile), *command], executable
    return _linux_command(command, run_dir, cwd, phase), executable


def _resolve_executable(command: list[str], cwd: Path) -> list[str]:
    executable = command[0]
    if "/" in executable:
        path = Path(executable)
        path = path if path.is_absolute() else cwd / path
    else:
        found = shutil.which(executable)
        if not found:
            raise ExecutionError(f"缺少执行工具：{executable}")
        path = Path(found)
    path = path.resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ExecutionError(f"执行文件不可用：{path}")
    return [str(path), *map(str, command[1:])]


def _terminate(process: subprocess.Popen, sig: int) -> None:
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        pass


def run_command(command: list[str], *, cwd: Path, run_dir: Path,
                phase: str, timeout: float) -> int:
    if phase not in {"compile", "simulate"}:
        raise ExecutionError(f"未知执行阶段：{phase}")
    if sys.platform not in {"darwin", "linux"}:
        raise ExecutionError(f"不支持的评测平台：{sys.platform}")
    run_dir, cwd = Path(run_dir).resolve(), Path(cwd).resolve()
    if not cwd.is_relative_to(run_dir):
        raise ExecutionError("执行工作目录必须位于本次运行目录内。")
    cwd.mkdir(parents=True, exist_ok=True)
    resolved = _resolve_executable(command, cwd)
    wrapped, _ = _wrap_command(resolved, run_dir, cwd, phase)
    environment = command_environment(run_dir)
    if sys.platform == "linux":
        environment = sandbox_environment()
    child = [sys.executable, "-I", str(Path(__file__).resolve()), "--child",
             str(math.ceil(timeout)), *wrapped]
    print(f"[{phase}] cwd={cwd}\n$ {shlex.join(command)}", flush=True)
    process = subprocess.Popen(child, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                               stdout=None, stderr=subprocess.STDOUT, start_new_session=True)
    previous_handler = None

    def interrupted(signum, frame):
        _terminate(process, signal.SIGTERM)
        raise ExecutionError("评测进程已中止。")

    if threading.current_thread() is threading.main_thread():
        previous_handler = signal.signal(signal.SIGTERM, interrupted)
    try:
        try:
            returncode = process.wait(timeout=timeout)
            print(f"[{phase}] exit={returncode}", flush=True)
            return returncode
        except subprocess.TimeoutExpired as error:
            raise ExecutionTimeout(f"{phase} 超过 {timeout:g} 秒。") from error
    finally:
        # 子进程退出后仍清理其进程组，覆盖编译器留下的子进程。
        _terminate(process, signal.SIGTERM)
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            _terminate(process, signal.SIGKILL)
            process.wait()
        _terminate(process, signal.SIGKILL)
        if previous_handler is not None:
            signal.signal(signal.SIGTERM, previous_handler)


def _child() -> None:
    timeout = int(sys.argv[2])
    command = sys.argv[3:]
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (timeout + 1, timeout + 2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (512, 512))
    os.execv(command[0], command)


if __name__ == "__main__":
    if len(sys.argv) < 4 or sys.argv[1] != "--child":
        raise SystemExit("此程序由评测执行器调用。")
    _child()
