import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from sim.convert_edif import convert


ROOT = Path(__file__).resolve().parents[1]
CASES = [(2, 10), (3, 5), (-3, 5), (0, 7), (7, 0),
         (7, 1), (2, 32), (0x80000000, 2), (0xffffffff, 2), (0xffffffff, 31)]


def test_fastpow_on_supplied_cpu_edf(tmp_path):
    prefix = os.environ.get('RISCV_PREFIX', 'riscv64-unknown-elf-')
    commands = [prefix + 'as', prefix + 'ld', prefix + 'objcopy', 'iverilog', 'vvp']
    missing = [command for command in commands if shutil.which(command) is None]
    if missing:
        pytest.skip('未安装 ' + '、'.join(missing))
    temporary = tmp_path / 'tmp'
    temporary.mkdir()
    environment = {**os.environ, 'TMPDIR': str(temporary),
                   'TMP': str(temporary), 'TEMP': str(temporary)}
    expected = [pow(base, exponent, 1 << 32) for base, exponent in CASES]
    source = ['.option norvc', '.option norelax', '.section .text.verify,"ax"',
              '.globl verify_start', 'verify_start:', 'addi sp,zero,1024']
    for index, ((base, exponent), answer) in enumerate(zip(CASES, expected)):
        source += [f'li a0,0x{base & 0xffffffff:08x}', f'li a1,{exponent}',
                   'jal ra,fastpow', f'sw a0,{512 + 4 * index}(zero)',
                   f'li t0,0x{answer:08x}', 'bne a0,t0,.Lverify_fail']
    source += ['li t0,0x8c889292', 'jal zero,.Lverify_display', '.Lverify_fail:',
               'li t0,0x8e88f9c7', '.Lverify_display:', 'lui t1,0xe0000',
               'sw t0,0(t1)', '.Lverify_halt:', 'jal zero,.Lverify_halt',
               '.include "programs/fastpow.S"']
    (tmp_path / 'cases.S').write_text('\n'.join(source) + '\n')
    (tmp_path / 'cases.ld').write_text(
        'ENTRY(verify_start)\nSECTIONS { .text 0 : { *(.text.verify) *(.text) } }\n')
    for command in [
        [prefix + 'as', '-march=rv32i', '-mabi=ilp32', '-mno-relax', '-I', str(ROOT),
         '-o', 'cases.o', 'cases.S'],
        [prefix + 'ld', '-m', 'elf32lriscv', '--no-relax', '-T', 'cases.ld',
         '-o', 'cases.elf', 'cases.o'],
        [prefix + 'objcopy', '-O', 'binary', '-j', '.text', 'cases.elf', 'cases.bin'],
    ]:
        subprocess.run(command, cwd=tmp_path, env=environment, check=True,
                       capture_output=True, text=True, timeout=30)
    image = (tmp_path / 'cases.bin').read_bytes()
    words = [int.from_bytes(image[index:index + 4], 'little')
             for index in range(0, len(image), 4)]
    (tmp_path / 'program.hex').write_text(''.join(
        f'{word:08x}\n' for word in words + [0x13] * (1024 - len(words))))
    netlists = []
    for name in ('SCPU', 'MIO_BUS', 'SSeg7', 'Multi_8CH32', 'SPIO', 'dm_controller'):
        destination = tmp_path / f'{name}.v'
        convert(ROOT / 'edf_file' / f'{name}.edf', destination)
        netlists.append(str(destination))
    sources = [ROOT / path for path in (
        'sim/vendor/xilinx_cells_sim.v', 'IO/clk_div.v', 'IO/Enter.v',
        'IO/Counter_3_IO.v', 'sim/memory.v', 'main.v', 'tests/tb_fastpow.v')]
    compiled = subprocess.run(
        ['iverilog', '-g2012', '-s', 'tb_fastpow',
         '-P', f'tb_fastpow.EXPECT_CASES={len(CASES)}', '-o', 'cases.vvp',
         *map(str, sources), *netlists], cwd=tmp_path, env=environment,
        capture_output=True, text=True, timeout=60)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    simulated = subprocess.run(['vvp', 'cases.vvp'], cwd=tmp_path, env=environment,
                               capture_output=True, text=True, timeout=60)
    assert simulated.returncode == 0, simulated.stdout + simulated.stderr
    results = [(int(index), int(word, 16)) for index, word in re.findall(
        r'result\[(\d+)\]=([0-9a-f]{8})', simulated.stdout)]
    assert results == list(enumerate(expected))
    display = re.search(r'Disp_num=([0-9a-f]{8})', simulated.stdout)
    assert display is not None and int(display[1], 16) == 0x8c889292
