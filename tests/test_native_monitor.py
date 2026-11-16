from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sim"))
from animation import EXPECTED_FRAMES, LOOP_END, LOOP_START, animation_word, inspect_frames
from evaluate import compiler_environment_failure


def evidence_frames():
    # 仅构造纯判定函数的确定性输入，不替代或模拟任何 CPU 执行。
    return [{"index": index, "cycle": index * 1_000_100 + 100,
             "time_ns": (index * 1_000_100 + 100) * 160,
             "pc": "000001f4" if index >= 6 else "00000260",
             "word": f'{expected["word"]:08x}', "phase": expected["phase"]}
            for index, expected in enumerate(EXPECTED_FRAMES)]


class AnimationEvidenceTests(unittest.TestCase):
    def test_complete_loop_requires_four_moves_and_eight_blinks(self):
        accepted, checks, loop = inspect_frames(evidence_frames())
        self.assertTrue(accepted)
        self.assertTrue(all(check["passed"] for check in checks))
        self.assertEqual(loop, {"start_frame": LOOP_START, "end_frame": LOOP_END,
                                "period_frames": 72, "right_moves": 4, "blinks": 8})

    def test_no_frames_never_passes_order_check(self):
        accepted, checks, loop = inspect_frames([])
        self.assertFalse(accepted)
        self.assertIsNone(loop)
        order = next(check for check in checks if check["name"] == "真实寄存器帧顺序")
        self.assertFalse(order["passed"])

    def test_first_ac_is_not_success(self):
        accepted, _, loop = inspect_frames(evidence_frames()[:LOOP_START + 1])
        self.assertFalse(accepted)
        self.assertIsNone(loop)

    def test_final_return_must_be_observed(self):
        self.assertFalse(inspect_frames(evidence_frames()[:-1])[0])

    def test_missing_blank_fails(self):
        frames = evidence_frames()
        frames[6 + 11]["word"] = frames[6 + 10]["word"]
        self.assertFalse(inspect_frames(frames)[0])

    def test_missing_flash_on_fails(self):
        frames = evidence_frames()
        frames[6 + 12]["word"] = "ffffffff"
        self.assertFalse(inspect_frames(frames)[0])

    def test_wrong_direction_fails(self):
        frames = evidence_frames()
        for step in range(18):
            frames[6 + 18 + step]["word"] = f"{animation_word(step, 2):08x}"
        self.assertFalse(inspect_frames(frames)[0])

    def test_stuck_ac_fails(self):
        frames = evidence_frames()
        for frame in frames[LOOP_START + 1:]:
            frame["word"] = frames[LOOP_START]["word"]
        self.assertFalse(inspect_frames(frames)[0])

    def test_reordered_or_reused_time_fails(self):
        frames = evidence_frames()
        frames[20]["cycle"] = frames[19]["cycle"]
        self.assertFalse(inspect_frames(frames)[0])

    def test_failure_pc_is_never_accepted(self):
        frames = evidence_frames()
        frames[-1]["pc"] = "00000218"
        self.assertFalse(inspect_frames(frames)[0])

    def test_ac_word_and_right_rotation(self):
        self.assertEqual(animation_word(10, 1), 0xff88c6ff)
        self.assertEqual(animation_word(10, 0), 0xffff88c6)
        self.assertEqual(animation_word(10, 3), 0xc6ffff88)
        self.assertEqual(animation_word(10, 2), 0x88c6ffff)


def test_environment_compiler_failure_is_detected(tmp_path):
    directory = tmp_path / "logs"
    directory.mkdir()
    log = directory / "run.log"
    log.write_text("cc1plus: warning: ./x.gch: had text segment at different address\n")
    assert compiler_environment_failure(tmp_path)
    log.write_text("error: syntax error in SCPU.v\n")
    assert not compiler_environment_failure(tmp_path)


if __name__ == "__main__":
    unittest.main()
