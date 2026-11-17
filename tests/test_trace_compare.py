import json
from pathlib import Path
import struct

import pytest

from sim.trace_compare import RECORD, TraceComparison, decode_record


@pytest.fixture
def evidence():
    # 服务器真实八文件 RTL 与可信 EDF 复放的采样窗口。
    path = Path(__file__).parent / 'fixtures/first-diff-rtl.json'
    return json.loads(path.read_text())


def payload(row):
    cycle, timestamp = row['cycle'], row['time_ns']
    names = ('pc', 'next_pc', 'instruction', 'address', 'store_data', 'load_data')
    words = [cycle & 0xffffffff, cycle >> 32, timestamp & 0xffffffff, timestamp >> 32]
    words += [int(row[name], 16) for name in names]
    words += [row['mem_w'], row['dm_ctrl'], int(row['display_word'], 16), int(row['registers'] is not None)]
    registers = row['registers']
    words += ([int(registers[name], 16) for name in
               ('ra', 'sp', 's0', 's1', 'a0', 'a1', 'a2', 'a3', 's2', 's3')]
              if registers is not None else [0] * 10)
    return RECORD.pack(*words)


def test_first_branch_difference_keeps_context_and_ignores_later_differences(evidence):
    comparison = TraceComparison()
    for expected, actual in zip(evidence['expected'], evidence['actual']):
        done = comparison.add_payload(payload(expected), payload(actual))
    assert done
    report = comparison.finish()
    assert report['first_cycle'] == report['compared_through_cycle'] == 327
    assert report['fields'] == ['next_pc']
    assert [row['cycle'] for row in report['expected']] == list(range(317, 338))
    assert [row['cycle'] for row in report['actual']] == list(range(317, 338))
    assert report['expected'][10]['next_pc'] == '000003d4'
    assert report['actual'][10]['next_pc'] == '00000400'
    assert report['expected'][11]['instruction'] != report['actual'][11]['instruction']
    assert report['expected'][10]['registers']['s1'] == report['expected'][10]['registers']['s3']
    assert all(row['registers'] is None for row in report['actual'])


def test_early_eof_preserves_only_available_actual_context(evidence):
    comparison = TraceComparison()
    for index, expected in enumerate(evidence['expected']):
        actual = evidence['actual'][index] if index < 10 else None
        comparison.add_payload(payload(expected), payload(actual) if actual else None)
    report = comparison.finish()
    assert report['first_cycle'] == 327
    assert report['fields'] == ['eof']
    assert report['actual_eof'] and not report['expected_eof']
    assert [row['cycle'] for row in report['actual']] == list(range(317, 327))
    assert [row['cycle'] for row in report['expected']] == list(range(317, 338))


def test_first_sample_difference_does_not_invent_previous_rows(evidence):
    comparison = TraceComparison()
    for expected, actual in zip(evidence['expected'][10:], evidence['actual'][10:]):
        comparison.add_payload(payload(expected), payload(actual))
    report = comparison.finish()
    assert report['first_cycle'] == 327
    assert [row['cycle'] for row in report['expected']] == list(range(327, 338))
    assert [row['cycle'] for row in report['actual']] == list(range(327, 338))


def test_equal_observed_prefix_has_no_failure_claim(evidence):
    comparison = TraceComparison()
    for row in evidence['expected']:
        comparison.add_payload(payload(row), payload(row))
    assert comparison.add_payload(None, None)
    report = comparison.finish()
    assert report['status'] == 'identical_prefix'
    assert report['first_cycle'] is None and report['fields'] == []
    assert report['compared_through_cycle'] == 337
    assert [row['cycle'] for row in report['expected']] == list(range(328, 338))
    assert report['expected_eof'] and report['actual_eof']


def test_incomplete_binary_record_is_rejected(evidence):
    truncated = payload(evidence['expected'][0])[:-1]
    with pytest.raises(struct.error):
        decode_record(truncated)
    with pytest.raises(struct.error):
        TraceComparison().add_payload(truncated, truncated)
