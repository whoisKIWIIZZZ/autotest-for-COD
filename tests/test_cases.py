from sim.cases import AC_WORD, CASES, FAIL_WORD, inspect_case_frames


def frame(index, word, *, cycle=None):
    cycle = index + 1 if cycle is None else cycle
    return {"index": index, "word": f"{word:08x}", "cycle": cycle,
            "time_ns": cycle * 160, "pc": "000001f4", "phase": "animation"}


def test_simple_ac_completes_on_first_whole_word():
    passed, checks, loop = inspect_case_frames(CASES["testac-simple"], [frame(0, AC_WORD)])
    assert passed and all(check["passed"] for check in checks)
    assert loop is None


def test_simple_ac_allows_other_display_values_before_completion():
    passed, _, _ = inspect_case_frames(CASES["testac-simple"], [frame(0, 0xFFFFFFFF), frame(1, AC_WORD)])
    assert passed


def test_partial_ac_is_not_completion():
    assert not inspect_case_frames(CASES["testac-simple"], [frame(0, 0xFF88FFFF)])[0]


def test_success_word_still_requires_valid_time_evidence():
    frames = [frame(0, 0xFFFFFFFF), frame(1, AC_WORD, cycle=1)]
    assert not inspect_case_frames(CASES["testac-simple"], frames)[0]


def test_failure_display_cannot_be_followed_by_success():
    spec = CASES["fastpow"]
    frames = [frame(0, FAIL_WORD), frame(1, spec.success_word)]
    assert not inspect_case_frames(spec, frames)[0]


def test_simple_ac_rejects_failure_pc():
    failed = frame(0, AC_WORD)
    failed["pc"] = "00000218"
    assert not inspect_case_frames(CASES["testac-simple"], [failed])[0]
