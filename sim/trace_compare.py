import json
import os
import struct
import tempfile
from collections import deque
from pathlib import Path


HEADER = struct.Struct('<4I')
RECORD = struct.Struct('<24I')
_REGISTER_NAMES = ('ra', 'sp', 's0', 's1', 'a0', 'a1', 'a2', 'a3', 's2', 's3')
_INTERFACE = struct.Struct('<9I')
_CYCLE = struct.Struct('<Q')
_INTERFACE_FIELDS = ('pc', 'next_pc', 'instruction', 'address', 'store_data',
                     'load_data', 'mem_w', 'dm_ctrl', 'display_word')
_ALWAYS_FIELDS = ((0, 'pc'), (1, 'next_pc'), (2, 'instruction'),
                  (6, 'mem_w'), (8, 'display_word'))
_CONTEXT = 10


def decode_record(payload: bytes) -> dict:
    words = RECORD.unpack(payload)
    row = {
        'cycle': words[0] | (words[1] << 32),
        'time_ns': words[2] | (words[3] << 32),
    }
    for index, name in enumerate(('pc', 'next_pc', 'instruction', 'address',
                                  'store_data', 'load_data'), start=4):
        row[name] = f'{words[index]:08x}'
    row.update(mem_w=words[10], dm_ctrl=words[11],
               display_word=f'{words[12]:08x}', registers=None)
    if words[13] & 1:
        row['registers'] = {
            name: f'{value:08x}'
            for name, value in zip(_REGISTER_NAMES, words[14:])
        }
    return row


def _interface_values(row):
    if isinstance(row, bytes):
        return _INTERFACE.unpack_from(row, 16)
    return tuple(row[name] if index in (6, 7) else int(row[name], 16)
                 for index, name in enumerate(_INTERFACE_FIELDS))


def _row_cycle(row):
    return _CYCLE.unpack_from(row)[0] if isinstance(row, bytes) else row['cycle']


def _decoded_row(row):
    return decode_record(row) if isinstance(row, bytes) else row


def _different_fields(expected, actual) -> list:
    fields = [name for index, name in _ALWAYS_FIELDS if expected[index] != actual[index]]
    if expected[2] != actual[2]:
        return fields
    instruction = expected[2]
    opcode = instruction & 0x7f
    if opcode not in (0x03, 0x23):
        return fields
    for index, name in ((3, 'address'), (7, 'dm_ctrl')):
        if expected[index] != actual[index]:
            fields.append(name)
    if opcode == 0x03:
        if expected[5] != actual[5]:
            fields.append('load_data')
    else:
        # SB/SH 的高位不参与写入；保留原始采样值用于诊断。
        funct3 = (instruction >> 12) & 7
        width = 8 if funct3 == 0 else 16 if funct3 == 1 else 32
        mask = (1 << width) - 1
        if (expected[4] & mask) != (actual[4] & mask):
            fields.append('store_data')
    return fields


class TraceComparison:
    def __init__(self):
        self._history = deque(maxlen=_CONTEXT)
        self._expected = []
        self._actual = []
        self._fields = []
        self._different = False
        self._done = False
        self._first_cycle = None
        self._compared_through_cycle = 0
        self._after = 0
        self._expected_eof = False
        self._actual_eof = False

    def add(self, expected: dict | None, actual: dict | None) -> bool:
        return self._add(expected, actual)

    def add_payload(self, expected: bytes | None, actual: bytes | None) -> bool:
        return self._add(expected, actual)

    def _add(self, expected, actual) -> bool:
        if self._done:
            return True
        # EOF 是终态；短流不补造记录，也不再恢复。
        if self._expected_eof:
            expected = None
        if self._actual_eof:
            actual = None
        for row in (expected, actual):
            if isinstance(row, bytes) and len(row) != RECORD.size:
                raise struct.error(f'trace record must contain exactly {RECORD.size} bytes')
        self._expected_eof |= expected is None
        self._actual_eof |= actual is None
        if expected is None and actual is None:
            self._done = True
            return True

        if self._different:
            if expected is not None:
                self._expected.append(expected)
            if actual is not None:
                self._actual.append(actual)
            self._after += 1
            self._done = self._after == _CONTEXT
            return self._done

        cycle = _row_cycle(expected if expected is not None else actual)
        self._compared_through_cycle = cycle
        fields = (['eof'] if expected is None or actual is None
                  else _different_fields(_interface_values(expected), _interface_values(actual)))
        if not fields:
            self._history.append((expected, actual))
            return False

        self._different = True
        self._first_cycle = cycle
        self._fields = fields
        self._expected = [pair[0] for pair in self._history]
        self._actual = [pair[1] for pair in self._history]
        self._history.clear()
        if expected is not None:
            self._expected.append(expected)
        if actual is not None:
            self._actual.append(actual)
        return False

    def finish(self, reason: str = '') -> dict:
        self._done = True
        if self._different:
            expected, actual = self._expected, self._actual
            default_reason = ('一侧记录流先结束，另一侧仍有实际 CPU 记录。'
                              if self._fields == ['eof']
                              else '检测到首个 CPU 公共接口行为差异。')
        else:
            expected = [pair[0] for pair in self._history]
            actual = [pair[1] for pair in self._history]
            default_reason = '已观测的 CPU 公共接口记录前缀相同；不代表未观测部分相同。'
        return {
            'version': 1,
            'status': 'different' if self._different else 'identical_prefix',
            'first_cycle': self._first_cycle,
            'compared_through_cycle': self._compared_through_cycle,
            'fields': list(self._fields),
            'context_before': _CONTEXT,
            'context_after': _CONTEXT,
            'expected': [_decoded_row(row) for row in expected],
            'actual': [_decoded_row(row) for row in actual],
            'expected_eof': self._expected_eof,
            'actual_eof': self._actual_eof,
            'reason': reason or default_reason,
            'trace_scope': 'public_cpu_interface',
            'reference': {'source': 'edf_file/SCPU.edf', 'sha256': '', 'cache_key': ''},
        }


def _render_row(row: dict, first_cycle) -> str:
    marker = '>>> 首差 ' if row['cycle'] == first_cycle else '    '
    signals = ' '.join(f'{name}={row[name]}' for name in
                       ('pc', 'next_pc', 'instruction', 'address', 'store_data',
                        'load_data', 'mem_w', 'dm_ctrl', 'display_word'))
    registers = row['registers']
    register_text = ('不可用（没有暴露内部寄存器接口）' if registers is None
                     else ' '.join(f'{name}={registers[name]}' for name in _REGISTER_NAMES))
    return (f"{marker}cycle={row['cycle']} time_ns={row['time_ns']} {signals} "
            f'registers={register_text}')


def _report_text(report: dict) -> str:
    status = report.get('status', 'error')
    first_cycle = report.get('first_cycle')
    lines = [
        '比较 PC 转移、写使能、显示字及有效访存行为。',
        '参考寄存器取自 EDF 触发器；提交侧展示 SCPU 公开接口。',
        f'状态：{status}',
        f"说明：{report.get('reason', '')}",
        f"参考：{report.get('reference', {}).get('source', 'edf_file/SCPU.edf')}",
        f"比较至周期：{report.get('compared_through_cycle', 0)}（首差后仅收集上下文，不再比较）",
        f"首差周期：{first_cycle if first_cycle is not None else '无可用首差'}",
        '首差字段：' + (', '.join(report.get('fields', [])) or '无'),
    ]
    if 'eof' in report.get('fields', []):
        lines.append('eof：首差周期一侧已结束，没有对应硬件记录；不补造该侧信号。')
    if status == 'identical_prefix':
        lines.append('未发现可观测差异；仅显示最近至多 10 条匹配记录，没有首差或首差后窗口。')
    if status in ('unavailable', 'error'):
        lines.append('该任务没有完整的复放诊断，详情见状态与说明。')

    for side, label in (('expected', '[预期行为]'), ('actual', '[错误行为]')):
        rows = report.get(side, [])
        lines.extend(('', label))
        lines.append('记录流：' + ('已观察到 EOF。' if report.get(f'{side}_eof', False)
                                  else '未观察到 EOF；窗口结束不表示程序结束。'))
        if first_cycle is not None:
            pivot = next((index for index, row in enumerate(rows)
                          if row['cycle'] == first_cycle), None)
            before = pivot if pivot is not None else len(rows)
            after = len(rows) - pivot - 1 if pivot is not None else 0
            lines.append(f'上下文：首差前 {before}/10 条，首差后 {after}/10 条。')
            if before < _CONTEXT:
                lines.append('首差前上下文不足：首差之前实际记录少于 10 条。')
            if after < _CONTEXT:
                lines.append('首差后上下文不足：执行流结束或采集停止。')
            if pivot is None:
                lines.append('首差周期无该侧记录（该侧已结束）；没有可显示的信号值。')
        if not rows:
            lines.append('没有可用的硬件采样记录。')
        lines.extend(_render_row(row, first_cycle) for row in rows)
    return '\n'.join(lines) + '\n'


def write_report(directory: Path, report: dict):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    contents = (
        ('first_diff.json', json.dumps(report, ensure_ascii=False, separators=(',', ':')) + '\n'),
        ('first_diff.txt', _report_text(report)),
    )
    staged = []
    try:
        for name, content in contents:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                             dir=directory, prefix=f'.{name}.',
                                             suffix='.tmp', delete=False) as stream:
                staged.append((Path(stream.name), directory / name))
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        for temporary, destination in staged:
            os.replace(temporary, destination)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
