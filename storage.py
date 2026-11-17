from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
from urllib.parse import quote

import psutil

from sim.cases import DEFAULT_CASE_IDS, select_cases, suite_evidence_complete
from sim.trace_compare import TraceComparison, write_report


ROOT = Path(__file__).resolve().parent
MAX_FILES = 64
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_PENDING = 20
STUDENT_FAILURES = {"wrong_answer", "compile_error", "time_limit"}
FINAL_STATUSES = {"accepted", "judge_error", "interrupted", *STUDENT_FAILURES}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def process_identity() -> tuple[int, float]:
    process = psutil.Process()
    return process.pid, process.create_time()


def controller_alive(pid: int | None, started: float | None) -> bool:
    if not pid or started is None:
        return False
    try:
        return psutil.Process(pid).create_time() == started
    except psutil.Error:
        return False


def write_json(path: Path, value) -> None:
    temporary = path.with_name(path.name + ".new")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


class QueueFull(RuntimeError):
    pass


class RunStore:
    def __init__(self, data_dir: Path = ROOT / "data"):
        self.data_dir = Path(data_dir).resolve()
        self.runs_dir = self.data_dir / "runs"
        self.database_path = self.data_dir / "submissions.sqlite3"

    @contextmanager
    def database(self):
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        with self.database() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id TEXT NOT NULL,
                    student_name TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('rtl','edf')),
                    is_debug INTEGER NOT NULL CHECK(is_debug IN (0,1)),
                    owner_digest TEXT,
                    state TEXT NOT NULL CHECK(state IN ('queued','running','finished')),
                    status TEXT NOT NULL,
                    score INTEGER CHECK(score IS NULL OR score IN (0,100)),
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    directory TEXT NOT NULL UNIQUE,
                    controller_pid INTEGER,
                    controller_started REAL,
                    result_json TEXT,
                    duration_seconds REAL,
                    CHECK(is_debug = (kind = 'edf'))
                );
                CREATE INDEX IF NOT EXISTS runs_owner ON runs(owner_digest,id DESC);
                CREATE INDEX IF NOT EXISTS runs_state ON runs(state);
                CREATE TABLE IF NOT EXISTS artifacts (
                    run_id INTEGER NOT NULL REFERENCES runs(id),
                    path TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    sha256 TEXT,
                    PRIMARY KEY(run_id,path)
                );
            """)
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(runs)")}
            if "duration_seconds" not in columns:
                connection.execute("ALTER TABLE runs ADD COLUMN duration_seconds REAL")
            missing = connection.execute(
                "SELECT id,result_json FROM runs WHERE duration_seconds IS NULL AND result_json IS NOT NULL"
            ).fetchall()
            for row in missing:
                try:
                    duration = json.loads(row["result_json"]).get("duration_seconds")
                except (ValueError, AttributeError):
                    continue
                if isinstance(duration, (int, float)) and not isinstance(duration, bool):
                    connection.execute("UPDATE runs SET duration_seconds=? WHERE id=?",
                                       (duration, row["id"]))
            interrupted = connection.execute(
                "SELECT * FROM runs WHERE state IN ('queued','running')"
            ).fetchall()
        for row in interrupted:
            if not controller_alive(row["controller_pid"], row["controller_started"]):
                directory = Path(row["directory"])
                directory.mkdir(parents=True, exist_ok=True)
                (directory / "logs").mkdir(exist_ok=True)
                with (directory / "logs" / "run.log").open("a", encoding="utf-8") as log:
                    log.write(f"\n[{now()}] 原控制进程已结束，评测标记为中断。\n")
                self.finish(row["id"], {
                    "status": "interrupted", "score": None,
                    "summary": "评测控制进程已结束，本次运行中断。日志与已有产物已保留。",
                    "checks": [],
                })

    def create(self, *, student_id: str, student_name: str, kind: str,
               owner_digest: str | None, files: list[tuple[str, Path]],
               case_ids=DEFAULT_CASE_IDS) -> dict:
        suite = select_cases(case_ids)
        if kind not in {"rtl", "edf"}:
            raise ValueError("提交类型必须为 rtl 或 edf。")
        pid, started = process_identity()
        with self.database() as connection:
            connection.execute("BEGIN IMMEDIATE")
            pending = connection.execute(
                "SELECT count(*) FROM runs WHERE state IN ('queued','running')"
            ).fetchone()[0]
            if pending >= MAX_PENDING:
                raise QueueFull("待评测提交已达到 20 条，请等待当前评测完成。")
            name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(6)
            directory = self.runs_dir / name
            directory.mkdir(mode=0o700)
            for child in ("submission", "logs", "tmp"):
                (directory / child).mkdir()
            created_at = now()
            cursor = connection.execute("""
                INSERT INTO runs(student_id,student_name,kind,is_debug,owner_digest,
                    state,status,summary,created_at,directory,controller_pid,controller_started)
                VALUES(?,?,?,?,?,'queued','queued','等待评测',?,?,?,?)
                """, (student_id, student_name, kind, int(kind == "edf"), owner_digest,
                      created_at, str(directory), pid, started))
            run_id = cursor.lastrowid
        with (directory / "logs" / "run.log").open("w", encoding="utf-8") as log:
            log.write(f"[{created_at}] run={run_id} kind={kind} debug={kind == 'edf'}\n")
        try:
            uploaded = []
            for filename, source in files:
                destination = directory / "submission" / filename
                shutil.copyfile(source, destination)
                with destination.open("rb") as incoming:
                    digest = hashlib.file_digest(incoming, "sha256").hexdigest()
                uploaded.append({"name": filename, "size": destination.stat().st_size,
                                 "sha256": digest})
            write_json(directory / "submission.json", {
                "id": run_id, "student_id": student_id, "student_name": student_name,
                "kind": kind, "is_debug": kind == "edf", "created_at": created_at,
                "files": uploaded, "suite": [spec.id for spec in suite],
            })
            self.index_artifacts(run_id, final=False)
        except Exception as error:
            with (directory / "logs" / "run.log").open("a", encoding="utf-8") as log:
                log.write(f"保存提交失败：{type(error).__name__}: {error}\n")
            self.finish(run_id, {"status": "judge_error", "score": None,
                                 "summary": "保存提交文件失败，已有文件和日志已保留。", "checks": []})
        return self.get(run_id)

    def get(self, run_id: int, owner_digest: str | None = None) -> dict | None:
        with self.database() as connection:
            sql, arguments = "SELECT * FROM runs WHERE id=?", [run_id]
            if owner_digest is not None:
                sql += " AND owner_digest=?"
                arguments.append(owner_digest)
            row = connection.execute(sql, arguments).fetchone()
        return dict(row) if row else None

    def list_runs(self, owner_digest: str, offset: int, limit: int) -> dict:
        with self.database() as connection:
            rows = connection.execute(
                "SELECT * FROM runs WHERE owner_digest=? ORDER BY id DESC LIMIT ? OFFSET ?",
                (owner_digest, limit, offset),
            ).fetchall()
            total = connection.execute(
                "SELECT count(*) FROM runs WHERE owner_digest=?", (owner_digest,)
            ).fetchone()[0]
        return {"runs": [self.view(dict(row)) for row in rows],
                "total": total, "offset": offset, "limit": limit}

    def start(self, run_id: int) -> bool:
        pid, started = process_identity()
        with self.database() as connection:
            cursor = connection.execute("""
                UPDATE runs SET state='running',status='running',summary='正在评测',
                    started_at=?,controller_pid=?,controller_started=?
                WHERE id=? AND state='queued'
                """, (now(), pid, started, run_id))
        return cursor.rowcount == 1

    def finish(self, run_id: int, result: dict) -> None:
        row = self.get(run_id)
        if row is None:
            raise ValueError("运行记录不存在。")
        result = dict(result)
        status = result.get("status")
        if status not in FINAL_STATUSES:
            result = {"status": "judge_error", "summary": "评测器返回了无效的结果状态。", "checks": []}
            status = "judge_error"
        if status == "accepted":
            submission = json.loads((Path(row["directory"]) / "submission.json").read_text())
            expected = submission.get("suite", list(DEFAULT_CASE_IDS))
            if not suite_evidence_complete(result, expected):
                result = {"status": "judge_error", "summary": "通过结果缺少所选程序的完整成功证据。", "checks": []}
                status = "judge_error"
        score = 100 if status == "accepted" else 0 if status in STUDENT_FAILURES else None
        result.update(score=score, kind=row["kind"], is_debug=bool(row["is_debug"]),
                      score_label="EDF 调试成绩" if row["is_debug"] else "RTL 成绩")
        directory = Path(row["directory"])
        if status != "accepted" and not result.get("first_diff"):
            report = next((item["first_diff"] for item in result.get("cases", [])
                           if item.get("first_diff")), None)
            if report is None:
                report = TraceComparison().finish("任务未完成硬件执行：" + str(result.get("summary", status)))
                report["status"] = "unavailable"
                write_report(directory / "work/runtime/run", report)
            result["first_diff"] = report
        write_json(directory / "result.json", result)
        with (directory / "logs" / "run.log").open("a", encoding="utf-8") as log:
            log.write(f"\n[{now()}] status={status} score={score} debug={bool(row['is_debug'])}\n")
        duration = result.get("duration_seconds")
        if not isinstance(duration, (int, float)) or isinstance(duration, bool):
            duration = None
        self.index_artifacts(run_id, final=True)
        with self.database() as connection:
            connection.execute("""
                UPDATE runs SET state='finished',status=?,score=?,summary=?,finished_at=?,
                    result_json=?,duration_seconds=? WHERE id=?
                """, (status, score, str(result.get("summary", status)), now(),
                      json.dumps(result, ensure_ascii=False), duration, run_id))

    def index_artifacts(self, run_id: int, *, final: bool) -> None:
        row = self.get(run_id)
        directory = Path(row["directory"])
        indexed = []
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(directory):
                continue
            relative = path.relative_to(directory).as_posix()
            if relative == "manifest.json" or relative.endswith(".new"):
                continue
            with path.open("rb") as content:
                digest = hashlib.file_digest(content, "sha256").hexdigest() if final else None
            indexed.append({"path": relative, "size": path.stat().st_size, "sha256": digest})
        if final:
            manifest = directory / "manifest.json"
            write_json(manifest, {"run_id": run_id, "files": indexed,
                                  "note": "manifest.json 自身由 SQL 文件索引记录。"})
            with manifest.open("rb") as content:
                digest = hashlib.file_digest(content, "sha256").hexdigest()
            indexed.append({"path": "manifest.json", "size": manifest.stat().st_size, "sha256": digest})
        with self.database() as connection:
            connection.execute("DELETE FROM artifacts WHERE run_id=?", (run_id,))
            connection.executemany(
                "INSERT INTO artifacts(run_id,path,size,sha256) VALUES(?,?,?,?)",
                [(run_id, item["path"], item["size"], item["sha256"]) for item in indexed],
            )

    def artifacts(self, run_id: int) -> list[dict]:
        with self.database() as connection:
            rows = connection.execute(
                "SELECT path,size,sha256 FROM artifacts WHERE run_id=? ORDER BY path", (run_id,)
            ).fetchall()
        return [{**dict(row), "url": f"/api/runs/{run_id}/files/{quote(row['path'], safe='/')}"}
                for row in rows]

    def artifact_path(self, run_id: int, relative: str) -> Path | None:
        row = self.get(run_id)
        if row is None:
            return None
        with self.database() as connection:
            indexed = connection.execute(
                "SELECT 1 FROM artifacts WHERE run_id=? AND path=?", (run_id, relative)
            ).fetchone()
        directory = Path(row["directory"]).resolve()
        path = directory / relative
        if (not indexed or path.is_symlink() or not path.is_file()
                or not path.resolve().is_relative_to(directory)):
            return None
        return path

    def leaderboard(self, limit: int) -> dict:
        with self.database() as connection:
            rows = connection.execute("""
                WITH formal AS (
                    SELECT * FROM runs
                    WHERE is_debug=0 AND state='finished' AND score IS NOT NULL
                )
                SELECT student_id,
                    (SELECT student_name FROM formal f2 WHERE f2.student_id=f.student_id
                     ORDER BY f2.id DESC LIMIT 1) AS student_name,
                    MAX(score) AS best_score,
                    SUM(CASE WHEN status='accepted' THEN 1 ELSE 0 END) AS accepted_runs,
                    COUNT(*) AS formal_runs,
                    MIN(CASE WHEN status='accepted' THEN finished_at END) AS first_accepted_at,
                    MAX(finished_at) AS last_finished_at
                FROM formal f
                GROUP BY student_id
                ORDER BY COALESCE(best_score,-1) DESC, accepted_runs DESC,
                    first_accepted_at IS NULL, first_accepted_at ASC, last_finished_at ASC
                LIMIT ?
            """, (limit,)).fetchall()
            total_students = connection.execute(
                "SELECT count(DISTINCT student_id) FROM runs "
                "WHERE is_debug=0 AND state='finished' AND score IS NOT NULL"
            ).fetchone()[0]
            debug_runs = connection.execute(
                "SELECT count(*) FROM runs WHERE is_debug=1"
            ).fetchone()[0]
        entries = []
        for position, row in enumerate(rows, start=1):
            entries.append({
                "rank": position, "student_id": row["student_id"],
                "student_name": row["student_name"],
                "best_score": row["best_score"], "accepted_runs": row["accepted_runs"],
                "formal_runs": row["formal_runs"],
                "first_accepted_at": row["first_accepted_at"],
                "last_finished_at": row["last_finished_at"],
            })
        return {"entries": entries, "students": total_students, "debug_runs": debug_runs,
                "rule": "只统计 RTL 正式提交；EDF 调试记录单列展示，不进入排名。"}

    def statistics(self) -> dict:
        with self.database() as connection:
            totals = connection.execute("""
                SELECT count(*) AS total,
                    SUM(is_debug=1) AS debug_runs,
                    SUM(is_debug=0) AS formal_runs,
                    SUM(status='accepted') AS accepted_runs,
                    SUM(status='accepted' AND is_debug=0) AS formal_accepted_runs,
                    SUM(status='accepted' AND is_debug=1) AS debug_accepted_runs,
                    SUM(state IN ('queued','running')) AS pending_runs,
                    avg(duration_seconds) AS average_duration
                FROM runs
            """).fetchone()
            students = connection.execute(
                "SELECT count(DISTINCT student_id) FROM runs WHERE is_debug=0"
            ).fetchone()[0]
            statuses = {row["status"]: row["count"] for row in connection.execute(
                "SELECT status, count(*) AS count FROM runs GROUP BY status"
            )}
        return {
            "total": totals["total"] or 0, "debug_runs": totals["debug_runs"] or 0,
            "formal_runs": totals["formal_runs"] or 0,
            "accepted_runs": totals["accepted_runs"] or 0,
            "formal_accepted_runs": totals["formal_accepted_runs"] or 0,
            "debug_accepted_runs": totals["debug_accepted_runs"] or 0,
            "pending_runs": totals["pending_runs"] or 0,
            "students": students, "statuses": statuses,
            "average_duration": totals["average_duration"],
        }

    def dashboard_runs(self, offset: int, limit: int, query: str = "",
                       kind: str | None = None, status: str | None = None,
                       debug: bool | None = None) -> dict:
        conditions = []
        arguments = []
        if query:
            conditions.append("(student_id LIKE ? OR student_name LIKE ?)")
            arguments.extend([f"%{query}%", f"%{query}%"])
        if kind:
            conditions.append("kind=?")
            arguments.append(kind)
        if status:
            conditions.append("status=?")
            arguments.append(status)
        if debug is not None:
            conditions.append("is_debug=?")
            arguments.append(int(debug))
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        with self.database() as connection:
            rows = connection.execute(
                f"SELECT * FROM runs{where} ORDER BY id DESC LIMIT ? OFFSET ?",
                (*arguments, limit, offset),
            ).fetchall()
            total = connection.execute(
                f"SELECT count(*) FROM runs{where}", arguments
            ).fetchone()[0]
        return {"runs": [self.dashboard_view(dict(row)) for row in rows],
                "total": total, "offset": offset, "limit": limit}

    def dashboard_view(self, row: dict) -> dict:
        result = json.loads(row["result_json"]) if row["result_json"] else None
        keys = ("id", "student_id", "student_name", "kind", "state", "status", "score",
                "summary", "created_at", "started_at", "finished_at", "duration_seconds")
        return {**{key: row[key] for key in keys}, "is_debug": bool(row["is_debug"]),
                "score_label": "EDF 调试成绩" if row["is_debug"] else "RTL 成绩",
                "run_dir": os.path.relpath(row["directory"], ROOT),
                "cycles": (result or {}).get("cycles"),
                "frames": sum(case.get("frames", 0) for case in result["cases"])
                if result and "cases" in result else ((result or {}).get("native") or {}).get("frames"),
                "result": result}

    @staticmethod
    def view(row: dict) -> dict:
        result = json.loads(row["result_json"]) if row["result_json"] else None
        keys = ("id", "student_id", "student_name", "kind", "state", "status", "score",
                "summary", "created_at", "started_at", "finished_at")
        return {**{key: row[key] for key in keys}, "is_debug": bool(row["is_debug"]),
                "score_label": "EDF 调试成绩" if row["is_debug"] else "RTL 成绩",
                "run_dir": os.path.relpath(row["directory"], ROOT), "result": result}
