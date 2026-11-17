from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import tempfile
import time

from execution import run_command
from sim.trace_compare import HEADER, RECORD, TraceComparison, write_report


ROOT = Path(__file__).resolve().parents[1]
PERIPHERALS = ('MIO_BUS', 'SSeg7', 'Multi_8CH32', 'SPIO', 'dm_controller')
DIAGNOSTIC_TIMEOUT = 5400


def file_digest(path):
    with Path(path).open('rb') as incoming:
        return hashlib.file_digest(incoming, 'sha256').hexdigest()


def unavailable_report(reason, status='unavailable'):
    report = TraceComparison().finish(reason)
    report['status'] = status
    return report


def save_unavailable(runtime, reason):
    report = unavailable_report(reason)
    write_report(runtime, report)
    return report


def _reference_binary(work, sources, run_dir):
    from convert_edif import convert
    from sim.evaluate import build_jobs

    reference_dir = work / 'reference'
    reference_dir.mkdir(exist_ok=True)
    cpu = work / 'edf/SCPU.edf'
    source_files = [sources / name for name in
                    ('xilinx_cells_sim.v', 'clk_div.v', 'Enter.v', 'Counter_3_IO.v',
                     'memory.v', 'main.v', 'judge_top.v', 'run_testac.cpp',
                     'trace_stream.h', 'monitor_config.h', 'convert_edif.py')]
    inputs = {path.name: file_digest(path) for path in source_files}
    inputs.update({name + '.edf': file_digest(work / 'edf' / (name + '.edf'))
                   for name in PERIPHERALS})
    inputs['SCPU.edf'] = file_digest(cpu)
    verilator = shutil.which('verilator')
    if verilator is None:
        raise RuntimeError('缺少 Verilator，无法构建可信 EDF 参考')
    version = subprocess.check_output([verilator, '--version'], text=True).strip()
    identity = {'stream_version': 1, 'sources': inputs, 'verilator': version,
                'machine': os.uname().machine}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    reference = {'source': 'edf_file/SCPU.edf', 'sha256': inputs['SCPU.edf'],
                 'cache_key': key}
    cache_root = ROOT / '.work/first-diff-reference'
    cache_root.mkdir(parents=True, exist_ok=True)
    cached = cache_root / key
    destination = reference_dir / 'Vjudge_top'
    with (cache_root / (key + '.lock')).open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if cached.exists():
            manifest = json.loads((cached / 'manifest.json').read_text())
            binary = cached / 'Vjudge_top'
            if (manifest['identity'] != identity or binary.is_symlink()
                    or file_digest(binary) != manifest['binary_sha256']):
                raise RuntimeError('可信 EDF 参考缓存完整性检查失败')
            shutil.copy2(binary, destination)
            print(f'可信 EDF 参考缓存命中：{key[:12]}', flush=True)
            return destination, reference

        print('构建可信 EDF 参考（全部六份 EDF）', flush=True)
        convert(cpu, reference_dir / 'SCPU.v')
        units = [sources / 'xilinx_cells_sim.v']
        units += [work / 'netlist' / (name + '.v') for name in PERIPHERALS]
        units += [sources / name for name in
                  ('clk_div.v', 'Enter.v', 'Counter_3_IO.v', 'memory.v',
                   'main.v', 'judge_top.v')]
        units.append(reference_dir / 'SCPU.v')
        command = [verilator, '--cc', '--exe', '--build', '-j', build_jobs(),
                   '--no-timing', '--timescale-override', '1ns/1ps',
                   '--top-module', 'judge_top', '--prefix', 'Vjudge_top',
                   '--Mdir', str(reference_dir / 'build'), '-O3', '-DSCPU_REFERENCE',
                   '-CFLAGS', '-O3 -march=native -DSCPU_REFERENCE', '-Wno-fatal',
                   '-Werror-MODDUP', '--output-split', '12000',
                   '--output-split-cfuncs', '1000', '-I' + str(sources)]
        command += list(map(str, units)) + [str(sources / 'run_testac.cpp')]
        code = run_command(command, cwd=work, run_dir=run_dir, phase='compile', timeout=1200)
        if code != 0:
            raise RuntimeError(f'可信 EDF 参考编译失败（退出码 {code}），请查看日志')
        binary = reference_dir / 'build/Vjudge_top'
        shutil.copy2(binary, destination)
        with tempfile.TemporaryDirectory(prefix='reference-', dir=cache_root) as temporary:
            staged = Path(temporary)
            shutil.copy2(binary, staged / 'Vjudge_top')
            manifest = {'identity': identity, 'binary_sha256': file_digest(binary)}
            (staged / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True) + '\n')
            staged.rename(cached)
    return destination, reference


class _StreamReader:
    def __init__(self, path, future, deadline):
        self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        self.keepalive = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
        self.future = future
        self.deadline = deadline
        self.buffer = b''
        self.offset = 0
        self.eof = False

    def _release_keepalive(self):
        if self.keepalive is not None:
            os.close(self.keepalive)
            self.keepalive = None

    def _read_exact(self, size):
        while len(self.buffer) - self.offset < size:
            if self.eof:
                if len(self.buffer) != self.offset:
                    raise ValueError('CPU 记录流在一条记录中途结束')
                return None
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('首差异复放超过时间上限')
            if self.future is not None and self.future.done():
                self._release_keepalive()
                self.future.result()
            ready, _, _ = select.select([self.fd], [], [], min(remaining, 0.25))
            if not ready:
                continue
            block = os.read(self.fd, 65536)
            if block:
                self.buffer = self.buffer[self.offset:] + block
                self.offset = 0
            else:
                self.eof = True
        result = self.buffer[self.offset:self.offset + size]
        self.offset += size
        return result

    def read_header(self):
        payload = self._read_exact(HEADER.size)
        if payload is None or HEADER.unpack(payload) != (0x46534431, 1, 24, 0):
            raise ValueError('CPU 记录流协议头缺失或不兼容')
        self._release_keepalive()

    def next_record(self):
        return self._read_exact(RECORD.size)

    def close(self):
        self._release_keepalive()
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def compare_replays(expected_binary, actual_binary, runtime, run_dir, case_id, cycles):
    replay = runtime / 'first-diff-replay'
    replay.mkdir(exist_ok=False)
    paths = [replay / name for name in ('expected', 'actual')]
    pipes = []
    readers = []
    futures = []
    comparison = TraceComparison()
    report = None
    errors = []
    deadline = time.monotonic() + DIAGNOSTIC_TIMEOUT
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='first-diff')
    try:
        for path in paths:
            path.mkdir()
            shutil.copy2(runtime / 'program.hex', path / 'program.hex')
            pipe = path / 'trace.fifo'
            os.mkfifo(pipe, 0o600)
            pipes.append(pipe)
            readers.append(_StreamReader(pipe, None, deadline))
        for binary, path, pipe, reader in zip(
                (expected_binary, actual_binary), paths, pipes, readers):
            command = [str(binary), '--case', case_id, '--stream', str(pipe),
                       '--max-cycles', str(cycles)]
            future = pool.submit(run_command, command, cwd=path, run_dir=run_dir,
                                 phase='simulate', timeout=DIAGNOSTIC_TIMEOUT)
            reader.future = future
            futures.append(future)
        for reader in readers:
            reader.read_header()
        while True:
            expected, actual = (reader.next_record() for reader in readers)
            if comparison.add_payload(expected, actual):
                break
        report = comparison.finish()
    except Exception as error:
        report = comparison.finish(f'复放诊断错误：{type(error).__name__}: {error}')
        if report['status'] != 'different':
            report['status'] = 'error'
    finally:
        for reader in readers:
            reader.close()
        for pipe in pipes:
            pipe.unlink(missing_ok=True)
        for future in futures:
            try:
                code = future.result()
                if code != 0:
                    errors.append(f'复放进程退出码 {code}')
            except Exception as error:
                errors.append(f'{type(error).__name__}: {error}')
        pool.shutdown(wait=True)
    if errors:
        report['reason'] += '；' + '；'.join(errors)
        if report['status'] != 'different':
            report['status'] = 'error'
    return report


def diagnose_failure(spec, binary, runtime, run_dir, work, sources, outcome):
    started = time.monotonic()
    reference = {'source': 'edf_file/SCPU.edf', 'sha256': '', 'cache_key': ''}
    native = outcome.get('native') or {}
    cycles = native.get('cycles', outcome.get('cycles', 0))
    try:
        if type(cycles) is not int or cycles < 0:
            raise ValueError('原评测 CPU 周期证据无效')
        if not native and cycles == 0:
            report = unavailable_report('原仿真未留下可用于复放的 CPU 周期证据。')
        else:
            expected, reference = _reference_binary(work, sources, run_dir)
            report = compare_replays(expected, binary, runtime, run_dir, spec.id,
                                     max(1, cycles) + 11)
    except Exception as error:
        report = unavailable_report(f'诊断失败：{type(error).__name__}: {error}', 'error')
    report.update(case_id=spec.id, reference=reference,
                  duration_seconds=round(time.monotonic() - started, 6))
    program = runtime / 'program.hex'
    if program.is_file():
        report['program_sha256'] = file_digest(program)
    write_report(runtime, report)
    return report
