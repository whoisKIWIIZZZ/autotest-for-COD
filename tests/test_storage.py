from pathlib import Path

import pytest

from storage import RunStore
from sim.cases import select_cases


def program_evidence():
    cases = []
    for spec in select_cases():
        cases.append({**spec.public(), "status": "accepted", "cycles": 10, "frames": 1,
                      "checks": [{"name": "实际显示", "passed": True}], "loop": None,
                      "native": {"status": "accepted", "cycles": 10, "frames": 1,
                                 "display_word": f"{spec.success_word:08x}"}})
    return {"suite": [case["id"] for case in cases], "cases": cases, "cycles": 30}


@pytest.fixture
def store(tmp_path):
    instance = RunStore(tmp_path / "data")
    instance.initialize()
    return instance


def submit(store, tmp_path, student_id, kind, status, *, complete=False, evidence=None, name=None):
    filename = "SCPU.v" if kind == "rtl" else "SCPU.edf"
    upload = tmp_path / "uploads" / filename
    upload.parent.mkdir(exist_ok=True)
    upload.write_text("module SCPU; endmodule\n", encoding="utf-8")
    row = store.create(student_id=student_id, student_name=name or f"{student_id}-姓名",
                       kind=kind, owner_digest=None, files=[(filename, upload)])
    result = {"status": status, "summary": "测试结果", "checks": [], "duration_seconds": 1.25}
    if complete:
        result.update(program_evidence())
    if evidence is not None:
        result.update(evidence)
    store.finish(row["id"], result)
    return store.get(row["id"])


def test_leaderboard_only_ranks_formal_rtl_scores(store, tmp_path):
    submit(store, tmp_path, "debug-only", "edf", "accepted", complete=True)
    submit(store, tmp_path, "passing", "rtl", "accepted", complete=True)
    submit(store, tmp_path, "failing", "rtl", "wrong_answer")
    board = store.leaderboard(50)
    assert [entry["student_id"] for entry in board["entries"]] == ["passing", "failing"]
    assert board["entries"][0]["best_score"] == 100
    assert board["entries"][0]["accepted_runs"] == 1
    assert board["entries"][1]["best_score"] == 0
    assert board["debug_runs"] == 1
    assert board["students"] == 2


def test_unscored_environment_failure_is_not_ranked(store, tmp_path):
    submit(store, tmp_path, "env", "rtl", "judge_error")
    submit(store, tmp_path, "scored", "rtl", "wrong_answer")
    board = store.leaderboard(50)
    assert [entry["student_id"] for entry in board["entries"]] == ["scored"]
    assert board["students"] == 1


def test_best_formal_score_survives_repeated_submissions(store, tmp_path):
    submit(store, tmp_path, "repeat", "rtl", "compile_error")
    submit(store, tmp_path, "repeat", "rtl", "accepted", complete=True)
    entry = store.leaderboard(50)["entries"][0]
    assert entry["best_score"] == 100
    assert entry["formal_runs"] == 2
    assert entry["accepted_runs"] == 1


def test_statistics_separate_debug_and_formal(store, tmp_path):
    submit(store, tmp_path, "a", "edf", "accepted", complete=True)
    submit(store, tmp_path, "b", "rtl", "accepted", complete=True)
    submit(store, tmp_path, "c", "rtl", "time_limit")
    stats = store.statistics()
    assert (stats["total"], stats["formal_runs"], stats["debug_runs"]) == (3, 2, 1)
    assert (stats["formal_accepted_runs"], stats["debug_accepted_runs"]) == (1, 1)
    assert stats["students"] == 2
    assert stats["average_duration"] == pytest.approx(1.25)


def test_accepted_requires_observed_program_evidence(store, tmp_path):
    row = submit(store, tmp_path, "a", "rtl", "accepted")
    assert row["status"] == "judge_error"
    assert row["score"] is None


@pytest.mark.parametrize("failure", ["missing", "duplicate", "failed", "wrong_display", "cycle_total"])
def test_incomplete_or_inconsistent_suite_cannot_be_accepted(store, tmp_path, failure):
    evidence = program_evidence()
    if failure == "missing":
        evidence["cases"].pop()
    elif failure == "duplicate":
        evidence["cases"][1]["id"] = "fastpow"
    elif failure == "failed":
        evidence["cases"][1]["status"] = "wrong_answer"
    elif failure == "wrong_display":
        evidence["cases"][1]["native"]["display_word"] = "8e88f9c7"
    else:
        evidence["cycles"] += 1
    row = submit(store, tmp_path, "bad-evidence", "rtl", "accepted", evidence=evidence)
    assert row["status"] == "judge_error"
    assert row["score"] is None


def test_debug_score_is_labelled_and_kept_out_of_formal_ranking(store, tmp_path):
    row = submit(store, tmp_path, "debug", "edf", "accepted", complete=True)
    view = store.dashboard_view(row)
    assert view["status"] == "accepted"
    assert view["score"] == 100
    assert view["is_debug"] is True
    assert view["score_label"] == "EDF 调试成绩"
    assert view["result"]["score_label"] == "EDF 调试成绩"
    assert store.leaderboard(50)["entries"] == []


def test_dashboard_filters_and_artifact_index(store, tmp_path):
    submit(store, tmp_path, "alice", "rtl", "accepted", complete=True)
    submit(store, tmp_path, "alice", "edf", "accepted", complete=True)
    submit(store, tmp_path, "bob", "rtl", "wrong_answer")
    formal = store.dashboard_runs(0, 50, "alice", None, None, False)
    assert formal["total"] == 1
    assert formal["runs"][0]["kind"] == "rtl"
    debug = store.dashboard_runs(0, 50, "", None, None, True)
    assert debug["total"] == 1
    assert debug["runs"][0]["score_label"] == "EDF 调试成绩"
    searched = store.dashboard_runs(0, 50, "bob", "rtl", None, None)
    assert searched["total"] == 1
    run_id = searched["runs"][0]["id"]
    paths = {item["path"] for item in store.artifacts(run_id)}
    assert {"submission.json", "result.json", "logs/run.log", "manifest.json"} <= paths
    assert store.artifact_path(run_id, "../result.json") is None
    assert store.artifact_path(run_id, "manifest.json") is not None


def test_every_run_directory_is_retained_after_finish(store, tmp_path):
    row = submit(store, tmp_path, "a", "rtl", "wrong_answer")
    directory = Path(row["directory"])
    assert (directory / "logs" / "run.log").is_file()
    assert (directory / "submission" / "SCPU.v").is_file()
    assert (directory / "submission.json").is_file()
    assert (directory / "result.json").is_file()
    assert (directory / "manifest.json").is_file()
