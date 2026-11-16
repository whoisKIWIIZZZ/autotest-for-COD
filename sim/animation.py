SELFTEST_WORDS = tuple(stage * 0x00111100 for stage in range(1, 7))


def animation_word(step, position):
    # 原程序逐段形成 A、C；字节 0 是最右侧，循环右移是位置减一。
    left = (0, 16, 48, 49, 51, 115, 119)[min(step, 6)]
    right = (0, 1, 33, 49, 57)[max(0, min(step - 6, 4))]
    if step in (0, 11, 13, 17):
        left = right = 0
    return (~((left << (((position + 1) % 4) * 8)) |
              (right << (position * 8)))) & 0xffffffff


def expected_frames():
    frames = [{"word": word, "phase": "selftest"} for word in SELFTEST_WORDS]
    # 从第一个 AC 成形，到四次右移后同一位置再次成形，间隔必须是 72 帧。
    for offset in range(83):
        position = (1 - offset // 18) % 4
        step = offset % 18
        frames.append({"word": animation_word(step, position), "phase": "animation",
                       "position": position, "step": step})
    return frames


EXPECTED_FRAMES = expected_frames()
LOOP_START = 6 + 10
LOOP_END = 6 + 82


def inspect_frames(frames):
    checks = []
    mismatch = None
    previous_cycle = previous_time = -1
    for index, frame in enumerate(frames):
        if index >= len(EXPECTED_FRAMES):
            mismatch = f"多余的显示帧：{index}"
            break
        expected = EXPECTED_FRAMES[index]
        try:
            valid = (frame["index"] == index and
                     frame["word"] == f'{expected["word"]:08x}' and
                     frame["phase"] == expected["phase"] and
                     isinstance(frame["cycle"], int) and frame["cycle"] > previous_cycle and
                     isinstance(frame["time_ns"], int) and frame["time_ns"] > previous_time and
                     len(frame["pc"]) == 8 and int(frame["pc"], 16) != 0x218)
            previous_cycle, previous_time = frame["cycle"], frame["time_ns"]
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            mismatch = f"第 {index} 帧不符合原程序显示顺序或时间证据"
            break
    count = len(frames) if mismatch is None else index
    checks.append({"name": "六项启动自检显示", "passed": count >= 6,
                   "detail": f"已观测 {min(count, 6)}/6 项，须按原顺序出现"})
    checks.append({"name": "真实寄存器帧顺序", "passed": mismatch is None and count > 0,
                   "detail": mismatch or (f"已逐帧核对 {count} 个实际 Disp_num 写入结果"
                                          if count else "没有观测到任何实际显示帧")})
    checks.append({"name": "AC 逐段成形", "passed": count > LOOP_START,
                   "detail": "要求先逐段形成两个字符，不以首次出现 AC 判定通过"})
    full = mismatch is None and count == len(EXPECTED_FRAMES)
    checks.append({"name": "闪烁及四位置右移闭环", "passed": full,
                   "detail": "要求每个位置两次熄灭/点亮，并右移四次返回原位置 AC"})
    loop = None
    if full:
        loop = {"start_frame": LOOP_START, "end_frame": LOOP_END,
                "period_frames": LOOP_END - LOOP_START, "right_moves": 4, "blinks": 8}
    return full, checks, loop
