import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'sim'))
from sim.cases import CASES, select_cases
from sim.diagnostics import diagnose_failure, save_unavailable, unavailable_report
from sim.evaluate import compile_submission, snapshot
from sim.trace_compare import write_report
from storage import RunStore, now, write_json


def wait_for_idle(store):
    announced = False
    while True:
        with store.database() as connection:
            pending = connection.execute("SELECT count(*) FROM runs WHERE state IN ('queued','running')").fetchone()[0]
        if pending == 0:
            return
        if not announced:
            print('等待线上评测完成后补充历史诊断', flush=True)
            announced = True
        time.sleep(2)


def replay_workspace(directory, kind, cases):
    replica = directory / 'diagnostic-replay'
    replica.mkdir(exist_ok=False)
    for name in ('submission', 'logs', 'tmp'):
        (replica / name).mkdir()
    for key in ('TMPDIR', 'TMP', 'TEMP'):
        os.environ[key] = str(replica / 'tmp')
    for uploaded in (directory / 'submission').iterdir():
        if uploaded.is_symlink() or not uploaded.is_file():
            raise ValueError('历史提交文件缺失或包含符号链接')
        shutil.copy2(uploaded, replica / 'submission' / uploaded.name)
    suite = select_cases([item['id'] for item in cases])
    work, sources, runtime, uploads = snapshot(replica, kind, suite)
    original = directory / 'work'
    # 板级电路和 ROM 使用原归档，诊断探针与传输器使用当前版本。
    for name in ('main.v', 'clk_div.v', 'Enter.v', 'Counter_3_IO.v',
                 'memory.v', 'xilinx_cells_sim.v'):
        source = original / 'src' / name
        if not source.is_file():
            raise ValueError(f'历史归档缺少板级源码 {name}')
        shutil.copy2(source, sources / name)
    for name in ('MIO_BUS', 'SSeg7', 'Multi_8CH32', 'SPIO', 'dm_controller'):
        source = original / 'edf' / (name + '.edf')
        if not source.is_file():
            raise ValueError(f'历史归档缺少外设 {name}.edf')
        shutil.copy2(source, work / 'edf' / source.name)
    for spec in suite:
        source = original / 'runtime' / spec.id / 'program.hex'
        if not source.is_file() and len(suite) == 1:
            source = original / 'runtime/program.hex'
        if not source.is_file():
            raise ValueError(f'历史归档缺少 {spec.id} 的实际 ROM 映像')
        shutil.copy2(source, runtime / spec.id / 'program.hex')
    if compile_submission(work, sources, uploads, kind, replica) != 0:
        raise RuntimeError('历史提交复放编译失败，请查看补充诊断日志')
    return replica, work, sources, runtime, work / 'build/Vjudge_top'


def backfill(store, run_id):
    row = store.get(run_id)
    if row is None or row['state'] != 'finished' or row['status'] == 'accepted':
        return None
    result = json.loads(row['result_json']) if row['result_json'] else {}
    directory = Path(row['directory'])
    cases = result.get('cases')
    legacy = not isinstance(cases, list) or not cases
    if legacy:
        cases = [{**CASES['testac'].public(), 'status': row['status'],
                  'summary': row['summary'], 'cycles': result.get('cycles', 0),
                  'native': result.get('native')}]
    failed = [item for item in cases if item['status'] != 'accepted']
    missing = [item for item in failed if not item.get('first_diff')]
    if not missing:
        return None
    needs_replay = [item for item in missing if item['status'] in ('wrong_answer', 'time_limit')]
    prepared = None
    replay_error = None
    if needs_replay:
        try:
            prepared = replay_workspace(directory, row['kind'], cases)
        except Exception as error:
            replay_error = f'历史执行无法复放：{type(error).__name__}: {error}'
    added = []
    for item in missing:
        target = directory / 'work/runtime' / item['id']
        if item in needs_replay and prepared is not None:
            replica, work, sources, runtime, binary = prepared
            report = diagnose_failure(CASES[item['id']], binary, runtime / item['id'],
                                      replica, work, sources, item)
            write_report(target, report)
        elif item in needs_replay:
            report = unavailable_report(replay_error, 'error')
            write_report(target, report)
        else:
            report = save_unavailable(target, '该任务未完成硬件执行：' + str(item.get('summary', row['summary'])))
        item['first_diff'] = report
        if not legacy:
            write_json(target / 'result.json', item)
        added.append({'case_id': item['id'], 'status': report['status'],
                      'first_cycle': report['first_cycle'],
                      'fields': report['fields'],
                      'json_bytes': (target / 'first_diff.json').stat().st_size,
                      'text_bytes': (target / 'first_diff.txt').stat().st_size})
    result['first_diff'] = next(item['first_diff'] for item in failed if item.get('first_diff'))
    if not legacy:
        result['cases'] = cases
    serialized = json.dumps(result, ensure_ascii=False)
    with store.database() as connection:
        cursor = connection.execute(
            "UPDATE runs SET result_json=? WHERE id=? AND state='finished' AND result_json IS ?",
            (serialized, run_id, row['result_json']))
        if cursor.rowcount != 1:
            raise RuntimeError('历史记录在诊断期间发生变化，未覆盖数据库')
    write_json(directory / 'result.json', result)
    with (directory / 'logs/run.log').open('a') as log:
        log.write(f'\n[{now()}] 补充首差异诊断：{json.dumps(added, ensure_ascii=False)}\n')
    store.index_artifacts(run_id, final=True)
    summary = {'run_id': run_id, 'original_status': row['status'],
               'original_score': row['score'], 'diagnostics': added}
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description='为历史失败任务补充首差异，不重写原成绩和评测时间')
    parser.add_argument('--run-id', type=int, action='append')
    args = parser.parse_args()
    store = RunStore()
    work = ROOT / '.work'
    work.mkdir(exist_ok=True)
    with (work / 'backfill-first-diff.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.run_id:
            ids = args.run_id
        else:
            with store.database() as connection:
                ids = [row[0] for row in connection.execute(
                    "SELECT id FROM runs WHERE state='finished' AND status!='accepted' ORDER BY id")]
        completed = []
        for run_id in ids:
            wait_for_idle(store)
            summary = backfill(store, run_id)
            if summary is not None:
                completed.append(summary)
        write_json(work / 'backfill-first-diff.json', {'runs': completed})


if __name__ == '__main__':
    main()
