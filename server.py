import argparse
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import tempfile

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
import uvicorn

from judge import RunManager, validate_files
from storage import MAX_FILES, MAX_TOTAL_BYTES, ROOT, QueueFull, RunStore
from sim.cases import CASES, select_cases


WORK = ROOT / ".work"
for directory in (WORK / "tmp", WORK / "uploads"):
    directory.mkdir(parents=True, exist_ok=True)
os.environ["TMPDIR"] = str(WORK / "tmp")
tempfile.tempdir = str(WORK / "tmp")
OWNER_COOKIE = "scpu_owner"
DASHBOARD_TOKEN = ROOT / "data" / "dashboard-token"
STORE = RunStore()


def load_dashboard_token() -> bytes:
    override = os.environ.get("SCPU_DASHBOARD_TOKEN")
    if override:
        return override.encode("utf-8")
    DASHBOARD_TOKEN.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(DASHBOARD_TOKEN, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        DASHBOARD_TOKEN.chmod(0o600)
        token = DASHBOARD_TOKEN.read_text(encoding="utf-8").strip()
    else:
        token = secrets.token_urlsafe(32)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(token + "\n")
    if not token:
        raise RuntimeError("后台 token 文件为空，请配置有效的后台 token。")
    return token.encode("utf-8")


@asynccontextmanager
async def lifespan(app: FastAPI):
    STORE.initialize()
    app.state.dashboard_token = load_dashboard_token()
    print(f"后台 token 文件：{DASHBOARD_TOKEN}", flush=True)
    app.state.manager = RunManager(STORE)
    try:
        yield
    finally:
        await asyncio.to_thread(app.state.manager.close)


app = FastAPI(title="SCPU 自动评测", lifespan=lifespan, docs_url=None, redoc_url=None)
ALLOWED_HOSTS = [item.strip() for item in os.environ.get(
    "SCPU_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",") if item.strip()]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)


@app.middleware("http")
async def local_request_guard(request: Request, call_next):
    if request.method == "POST":
        origin = request.headers.get("origin")
        if origin and origin != f"http://{request.headers.get('host')}":
            return JSONResponse({"detail": "只接受本地同源网页提交。"}, status_code=403)
        if request.headers.get("content-type", "").split(";", 1)[0] != "multipart/form-data":
            return JSONResponse({"detail": "请使用多文件上传提交 SCPU。"}, status_code=415)
        length = request.headers.get("content-length", "")
        if not length.isdecimal() or "transfer-encoding" in request.headers:
            return JSONResponse({"detail": "提交需要有效的 Content-Length。"}, status_code=411)
        if int(length) > MAX_TOTAL_BYTES + 1024 * 1024:
            return JSONResponse({"detail": "提交文件合计不得超过 32 MiB。"}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'self'"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, error: RequestValidationError):
    return JSONResponse({"detail": "请检查学号、姓名、提交类型和文件。"}, status_code=422)


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/dashboard")
def dashboard_page():
    return FileResponse(ROOT / "static" / "dashboard.html")


@app.get("/leaderboard")
def leaderboard_page():
    return FileResponse(ROOT / "static" / "leaderboard.html")


@app.get("/api/config")
def config():
    return {"problem": "SCPU", "max_files": MAX_FILES, "max_total_bytes": MAX_TOTAL_BYTES,
            "kinds": ["rtl", "edf"], "cpu_hz": 6250000,
            "cases": [spec.public() for spec in select_cases()]}


def browser_owner(request: Request) -> str | None:
    token = request.cookies.get(OWNER_COOKIE, "")
    return token if re.fullmatch(r"[A-Za-z0-9_-]{43}", token) else None


def owner_digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def owned_run(run_id: int, request: Request) -> dict:
    token = browser_owner(request)
    row = STORE.get(run_id, owner_digest(token)) if token else None
    if row is None:
        raise HTTPException(404, "找不到这条运行记录。")
    return row


@app.post("/api/runs", status_code=202)
async def submit(request: Request, response: Response,
                 student_id: str = Form(...), student_name: str = Form(...),
                 kind: str = Form(...), files: list[UploadFile] = File(...)):
    try:
        student_id, student_name = student_id.strip(), student_name.strip()
        if not 1 <= len(student_id) <= 64 or not 1 <= len(student_name) <= 64:
            raise HTTPException(422, "学号和姓名须为 1–64 个字符。")
        try:
            validate_files(kind, [file.filename or "" for file in files])
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        if request.app.state.manager.stopping.is_set():
            raise HTTPException(503, "评测服务正在关闭。")
        owner = browser_owner(request) or secrets.token_urlsafe(32)
        with tempfile.TemporaryDirectory(prefix="upload-", dir=WORK / "uploads") as temporary:
            staged = []
            total_bytes = 0
            for file in files:
                destination = Path(temporary) / file.filename
                size = 0
                with destination.open("wb") as output:
                    while chunk := await file.read(128 * 1024):
                        size += len(chunk)
                        total_bytes += len(chunk)
                        if total_bytes > MAX_TOTAL_BYTES:
                            raise HTTPException(413, "提交文件合计不得超过 32 MiB。")
                        output.write(chunk)
                if size == 0:
                    raise HTTPException(422, f"文件为空：{file.filename}")
                staged.append((file.filename, destination))
            try:
                row = await asyncio.to_thread(
                    STORE.create, student_id=student_id, student_name=student_name,
                    kind=kind, owner_digest=owner_digest(owner), files=staged,
                )
            except QueueFull as error:
                raise HTTPException(429, str(error)) from error
        if row["state"] == "queued":
            request.app.state.manager.submit(row["id"])
        response.set_cookie(OWNER_COOKIE, owner, max_age=365 * 24 * 60 * 60,
                            httponly=True, samesite="strict", path="/")
        return STORE.view(row)
    finally:
        for file in files:
            await file.close()


@app.get("/api/runs")
def runs(request: Request, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    owner = browser_owner(request)
    if owner is None:
        return {"runs": [], "total": 0, "offset": offset, "limit": limit}
    return STORE.list_runs(owner_digest(owner), offset, limit)


def case_progress(row):
    directory = Path(row["directory"])
    result = json.loads(row["result_json"]) if row["result_json"] else None
    if result is not None and "cases" in result:
        return {"cases": result["cases"], "active_case": None}
    progress = directory / "work/runtime/progress.json"
    if result is None and progress.is_file() and not progress.is_symlink() and progress.resolve().is_relative_to(directory):
        try:
            data = json.loads(progress.read_text())
            select_cases([item["id"] for item in data["cases"]])
            return {"cases": data["cases"], "active_case": data["active_case"]}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(500, "评测用例进度文件无效，请查看日志。") from exc
    submission = json.loads((directory / "submission.json").read_text())
    ids = submission.get("suite")
    if ids is None:
        # 历史归档仍从原文件读取真实动画证据。
        historical = result or {}
        case = {**CASES["testac"].public(), "status": row["status"], "summary": row["summary"],
                "cycles": historical.get("cycles", 0), "frames": (historical.get("native") or {}).get("frames", 0),
                "checks": historical.get("checks", []), "native": historical.get("native"),
                "loop": historical.get("loop"), "duration_seconds": historical.get("duration_seconds", 0),
                "first_diff": historical.get("first_diff")}
        return {"cases": [case], "active_case": "testac" if row["state"] == "running" else None}
    return {"cases": [{**spec.public(), "status": row["status"] if row["state"] == "finished" else "queued",
                       "summary": row["summary"], "cycles": 0, "frames": 0, "checks": [], "loop": None,
                       "first_diff": (result or {}).get("first_diff")}
                      for spec in select_cases(ids)], "active_case": None}


@app.get("/api/runs/{run_id}")
def run(run_id: int, request: Request):
    row = owned_run(run_id, request)
    return {**STORE.view(row), **case_progress(row)}


@app.get("/api/runs/{run_id}/events")
def events(run_id: int, request: Request, case_id: str | None = Query(None, max_length=32)):
    row = owned_run(run_id, request)
    directory = Path(row["directory"])
    progress = case_progress(row)
    choices = {item["id"]: item for item in progress["cases"]}
    selected = case_id or progress["active_case"] or next(iter(choices), None)
    if selected not in choices:
        raise HTTPException(404, "这次提交没有该评测用例。")
    runtime = directory / "work/runtime"
    source = runtime / selected / "frames.jsonl"
    if selected == "testac" and not source.exists():
        source = runtime / "frames.jsonl"
    frames = []
    if source.is_file() and not source.is_symlink() and source.resolve().is_relative_to(directory):
        if source.stat().st_size > 8 * 1024 * 1024:
            raise HTTPException(413, "显示事件文件超过页面读取容量，请下载完整产物。")
        with source.open(encoding="utf-8") as incoming:
            for line in incoming:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    frames.append(item)
    selected_case = choices[selected]
    selected_case["frames"] = len(frames)
    if frames:
        selected_case["cycles"] = max(selected_case.get("cycles", 0), frames[-1]["cycle"])
    return {**progress, "case_id": selected, "frames": frames,
            "case_complete": selected_case["status"] not in {"queued", "running"},
            "complete": row["state"] == "finished"}


@app.get("/api/runs/{run_id}/log")
def log(run_id: int, request: Request, offset: int = Query(0, ge=0),
        limit: int = Query(65536, ge=1, le=262144)):
    row = owned_run(run_id, request)
    source = Path(row["directory"]) / "logs" / "run.log"
    if not source.is_file() or source.is_symlink():
        raise HTTPException(404, "日志文件不存在。")
    with source.open("rb") as incoming:
        incoming.seek(min(offset, source.stat().st_size))
        chunk = incoming.read(limit)
        next_offset = incoming.tell()
    return {"text": chunk.decode("utf-8", errors="replace"), "next_offset": next_offset,
            "complete": row["state"] == "finished" and next_offset >= source.stat().st_size}


@app.get("/api/runs/{run_id}/artifacts")
def artifacts(run_id: int, request: Request):
    owned_run(run_id, request)
    return {"files": STORE.artifacts(run_id)}


@app.get("/api/runs/{run_id}/files/{artifact_path:path}")
def download(run_id: int, artifact_path: str, request: Request):
    owned_run(run_id, request)
    path = STORE.artifact_path(run_id, artifact_path)
    if path is None:
        raise HTTPException(404, "找不到这份产物。")
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


def require_dashboard(request: Request) -> None:
    scheme, separator, token = request.headers.get("authorization", "").partition(" ")
    try:
        valid = secrets.compare_digest(token.encode("utf-8"), request.app.state.dashboard_token)
    except UnicodeEncodeError:
        valid = False
    if scheme.lower() != "bearer" or not separator or not token or not valid:
        raise HTTPException(401, "后台 token 无效。", headers={"WWW-Authenticate": "Bearer"})


def dashboard_run(run_id: int) -> dict:
    row = STORE.get(run_id)
    if row is None:
        raise HTTPException(404, "找不到这条运行记录。")
    return row


@app.get("/api/leaderboard")
def leaderboard(limit: int = Query(50, ge=1, le=200)):
    return {**STORE.leaderboard(limit), "stats": STORE.statistics()}


@app.get("/api/dashboard/runs")
def dashboard_runs(request: Request, offset: int = Query(0, ge=0),
                   limit: int = Query(50, ge=1, le=100), q: str = Query("", max_length=64),
                   kind: str | None = Query(None, pattern="^(rtl|edf)$"),
                   status: str | None = Query(None, max_length=32),
                   debug: bool | None = None):
    require_dashboard(request)
    data = STORE.dashboard_runs(offset, limit, q.strip(), kind, status, debug)
    return {**data, "stats": STORE.statistics()}


@app.get("/api/dashboard/runs/{run_id}")
def dashboard_run_detail(run_id: int, request: Request):
    require_dashboard(request)
    row = dashboard_run(run_id)
    view = {**STORE.dashboard_view(row), **case_progress(row)}
    directory = Path(row["directory"])
    log_path = directory / "logs" / "run.log"
    view["log_size"] = log_path.stat().st_size if log_path.is_file() else 0
    view["artifacts"] = STORE.artifacts(run_id)
    view["inputs"] = sorted(path.name for path in (directory / "submission").iterdir()) \
        if (directory / "submission").is_dir() else []
    return view


@app.get("/api/dashboard/runs/{run_id}/log")
def dashboard_log(run_id: int, request: Request, offset: int = Query(0, ge=0),
                  limit: int = Query(65536, ge=1, le=262144)):
    require_dashboard(request)
    row = dashboard_run(run_id)
    source = Path(row["directory"]) / "logs" / "run.log"
    if not source.is_file() or source.is_symlink():
        raise HTTPException(404, "日志文件不存在。")
    with source.open("rb") as incoming:
        incoming.seek(min(offset, source.stat().st_size))
        chunk = incoming.read(limit)
        next_offset = incoming.tell()
    size = source.stat().st_size
    return {"text": chunk.decode("utf-8", errors="replace"), "next_offset": next_offset,
            "size": size, "complete": row["state"] == "finished" and next_offset >= size}


@app.get("/api/dashboard/runs/{run_id}/files/{artifact_path:path}")
def dashboard_download(run_id: int, artifact_path: str, request: Request):
    require_dashboard(request)
    dashboard_run(run_id)
    path = STORE.artifact_path(run_id, artifact_path)
    if path is None:
        raise HTTPException(404, "找不到这份产物。")
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SCPU 多文件提交与完整动画循环评测")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认仅本机")
    arguments = parser.parse_args()
    if not 1 <= arguments.port <= 65535:
        parser.error("端口须在 1–65535 之间。")
    uvicorn.run(app, host=arguments.host, port=arguments.port)
