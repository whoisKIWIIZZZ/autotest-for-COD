from dataclasses import dataclass
import re

from sim.animation import EXPECTED_FRAMES, inspect_frames


PASS_WORD = 0x8C889292
FAIL_WORD = 0x8E88F9C7
AC_WORD = 0xFF88C6FF
MAX_RECORDED_FRAMES = 4096


@dataclass(frozen=True)
class CaseSpec:
    id: str
    label: str
    program: str
    success_word: int
    max_cycles: int
    failure_pc: int = 0xFFFFFFFF
    full_animation: bool = False

    def public(self):
        return {"id": self.id, "label": self.label, "success_word": f"{self.success_word:08x}"}


CASES = {
    "fastpow": CaseSpec("fastpow", "快速幂", "fastpow", PASS_WORD, 100_000),
    "fib": CaseSpec("fib", "递归 fib", "fib", PASS_WORD, 200_000),
    "testac-simple": CaseSpec("testac-simple", "完整 AC", "testac-simple", AC_WORD, 600_000_000, 0x218),
    "testac": CaseSpec("testac", "完整 AC 动画", "testac-simple", AC_WORD, 600_000_000, 0x218, True),
}
DEFAULT_CASE_IDS = ("fastpow", "fib", "testac-simple")


def select_cases(case_ids=DEFAULT_CASE_IDS):
    ids = tuple(case_ids)
    if not ids or len(ids) != len(set(ids)) or any(case_id not in CASES for case_id in ids):
        raise ValueError("评测用例必须为互不重复的 fastpow、fib、testac-simple 或 testac。")
    return tuple(CASES[case_id] for case_id in ids)


def inspect_case_frames(spec, frames):
    if spec.full_animation:
        return inspect_frames(frames)
    mismatch = None
    previous_cycle = previous_time = -1
    for index, frame in enumerate(frames):
        try:
            cycle, timestamp = frame["cycle"], frame["time_ns"]
            valid = (frame["index"] == index and type(cycle) is int and cycle > previous_cycle
                     and type(timestamp) is int and timestamp > previous_time
                     and re.fullmatch(r"[0-9a-f]{8}", frame["word"]) is not None
                     and re.fullmatch(r"[0-9a-f]{8}", frame["pc"]) is not None
                     and int(frame["pc"], 16) != spec.failure_pc)
            previous_cycle, previous_time = cycle, timestamp
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            mismatch = f"第 {index} 帧的索引、周期、时间或 PC 证据无效"
            break
        if spec.id in {"fastpow", "fib"} and frame["word"] == f"{FAIL_WORD:08x}":
            mismatch = "程序向数码管写入 FAIL"
            break
    reached = bool(frames) and frames[-1].get("word") == f"{spec.success_word:08x}"
    passed = mismatch is None and reached
    checks = [
        {"name": "真实数码管帧", "passed": mismatch is None and bool(frames),
         "detail": mismatch or f"已记录 {len(frames)} 个实际 Disp_num 写入结果"},
        {"name": "数码管完成标志", "passed": passed,
         "detail": f"目标 0x{spec.success_word:08x}，" + ("已观测" if reached else "尚未观测")},
    ]
    return passed, checks, None


def suite_evidence_complete(result, expected_ids):
    try:
        suite = select_cases(expected_ids)
        outcomes = result["cases"]
        if result["suite"] != [spec.id for spec in suite] or [item["id"] for item in outcomes] != list(expected_ids):
            return False
        total_cycles = 0
        for spec, outcome in zip(suite, outcomes):
            native = outcome["native"]
            if (outcome["status"] != "accepted" or native["status"] != "accepted"
                    or type(outcome["cycles"]) is not int or outcome["cycles"] <= 0
                    or native["cycles"] != outcome["cycles"]
                    or type(outcome["frames"]) is not int or outcome["frames"] <= 0
                    or native["frames"] != outcome["frames"]
                    or native["display_word"] != f"{spec.success_word:08x}"
                    or not outcome["checks"] or not all(check["passed"] is True for check in outcome["checks"])):
                return False
            if spec.full_animation:
                loop = outcome["loop"]
                if (loop["right_moves"] != 4 or loop["blinks"] != 8
                        or loop["end_frame"] - loop["start_frame"] != 72):
                    return False
            total_cycles += outcome["cycles"]
        return result["cycles"] == total_cycles
    except (KeyError, TypeError, ValueError):
        return False


def write_monitor_header(path, suite):
    words = ",".join(f'0x{frame["word"]:08x}U' for frame in EXPECTED_FRAMES)
    definitions = []
    for spec in suite:
        gap = min(spec.max_cycles, 32_000_000)
        definitions.append(
            f'{{"{spec.id}",0x{spec.success_word:08x}U,0x{spec.failure_pc:08x}U,'
            f'{spec.max_cycles}ULL,{gap}ULL,{str(spec.full_animation).lower()}' + '}')
    path.write_text(
        "#pragma once\n#include <cstddef>\n#include <cstdint>\n"
        "struct CaseSpec { const char* id; uint32_t success_word; uint32_t failure_pc; "
        "uint64_t max_cycles; uint64_t max_frame_gap; bool full_animation; };\n"
        f"constexpr uint32_t FAIL_WORD = 0x{FAIL_WORD:08x}U;\n"
        f"constexpr size_t MAX_RECORDED_FRAMES = {MAX_RECORDED_FRAMES};\n"
        f"constexpr uint32_t EXPECTED_WORDS[] = {{{words}}};\n"
        "constexpr size_t EXPECTED_COUNT = sizeof(EXPECTED_WORDS) / sizeof(EXPECTED_WORDS[0]);\n"
        "constexpr CaseSpec CASE_SPECS[] = {" + ",".join(definitions) + "};\n",
        encoding="ascii")
