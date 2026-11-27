"""Foreground A/C execution recipe; existing dual-loop optimizer, no new search policy."""
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
from statistics import mean
import subprocess
import sys
import time

from extension.host import resolve_host
from extension.pilot import execute
from extension.runner import save
from extension.baseline import initial_mean_reference, stable_mean_reference
from extension.evaluation import load_run
from extension.report import export

assert socket.gethostname() == 'bart'
BASE = Path(os.environ.get('TUXBOT_EXPERIMENT_DIR', 'results/silo-sysbench-02/run-01')).resolve()
QPS = int(os.environ.get('TUXBOT_SILO_QPS', '1000'))
SOURCE = Path('/work_dir/tailbench-src')
PYTHON = sys.executable
BINARY = SOURCE / 'tailbench/silo/out-perf.masstree/benchmarks/dbtest_integrated'
assert BINARY.is_file()
revision = subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip()
assert revision == '2f3098b539a9a3413086fc77e29637937bafd116'
assert subprocess.run(['pgrep', '-x', 'sysbench'], capture_output=True).returncode == 1
assert subprocess.run(['pgrep', '-f', '^([^ ]*/)?dbtest_integrated( |$)'], capture_output=True).returncode == 1

template = json.loads(Path('src/extension/examples/pilot-C.json').read_text())
host, _ = resolve_host(template['approved_host_parameters'])
initial_host = {name: control.read() for name, control in host.items()}
conditions = dict(
    silo=dict(program='TailBench Silo', revision=revision, executable_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
              workload='tpcc', scale_factor=4, threads=4, offered_qps=QPS, warmup_requests=1000,
              interval_seconds=1, metric='maximum interval sojourn p99 in window, ms', cpu_affinity=None),
    sysbench_cpu=dict(program='sysbench', version=subprocess.check_output(['sysbench', '--version'], text=True).strip(),
                      workload='cpu', threads=8, cpu_max_prime=50000, rand_seed=1, interval_seconds=1,
                      metric='mean interval events/s in window', cpu_affinity=None))
(BASE / 'configs').mkdir(parents=True, exist_ok=True)
save(BASE / 'experiment-status.json', dict(started=time.time(), completed=False, initial_host=initial_host,
     workload_conditions=conditions, relationship='hypothesized conflicting, not asserted in advance',
     baseline_policy='arithmetic mean of complete A stable phase; common tuner/report reference'))

for phase in ('A', 'C'):
    output = BASE / phase
    assert not output.exists(), 'Never overwrite a previous run'
    runtime = BASE / 'workloads' / phase
    workdir = runtime / 'silo'
    workdir.mkdir(parents=True, exist_ok=False)
    for name in ('out-perf.masstree', 'third-party'):
        (workdir / name).symlink_to(SOURCE / 'tailbench/silo' / name, target_is_directory=True)
    silo = dict(benchmark='tailbench', tailbench_app='silo', tailbench_root=str(runtime),
                tailbench_output_dir=str(workdir), results_dir=str(runtime / 'collector'),
                tailbench_threads=4, tailbench_qps=QPS, tailbench_silo_scale_factor=4,
                tailbench_warmupreqs=1000, tailbench_maxreqs=1000000000, tailbench_metrics_interval_sec=1)
    cpu = dict(workload='cpu', threads=8, cpu_max_prime=50000, metrics_file=str(output / 'cpu.intervals.jsonl'))
    silo_file, cpu_file = BASE / 'configs' / (phase + '-silo.json'), BASE / 'configs' / (phase + '-cpu.json')
    save(silo_file, silo)
    save(cpu_file, cpu)
    config = copy.deepcopy(template)
    config.update(mode='default' if phase == 'A' else 'coordinated', results_dir=str(output),
                  expected_initial_host=initial_host, defaults_verified=True,
                  baseline_aggregation='mean', reference_policy='stable_mean',
                  tuning_windows=30, stable_windows=20, window_seconds=5,
                  warmup_seconds=20, workload_conditions=conditions,
                  actor_model='gemini-3.5-flash', instant_model='gemini-3.5-flash-lite',
                  applications=[
                      dict(id='silo', metric='latency_p99', objective='minimize', bound='default', priority=1, ready_signal=True,
                           start=[PYTHON, '-m', 'extension.tailbench', 'serve', str(silo_file)],
                           measure=[PYTHON, '-m', 'extension.tailbench', 'measure', str(silo_file)]),
                      dict(id='sysbench_cpu', metric='events_per_second', objective='maximize', bound='default', priority=1, ready_signal=True,
                           start=[PYTHON, '-m', 'extension.sysbench', 'serve', str(cpu_file)],
                           measure=[PYTHON, '-m', 'extension.sysbench', 'measure', str(cpu_file)])])
    if phase == 'A':
        config.pop('cgroup_root', None)
        config.pop('reference_run', None)
    else:
        config['cgroup_root'] = '/sys/fs/cgroup/tuxbot-silo-sysbench-02-' + BASE.name + '-C'
        config['reference_run'] = str(BASE / 'A/results.json')
    filename = BASE / 'configs' / (phase + '.json')
    save(filename, config)
    print('START', phase, time.time(), flush=True)
    execute(filename, 'bart')
    assert subprocess.run(['pgrep', '-x', 'sysbench'], capture_output=True).returncode == 1, 'Leftover Sysbench'
    assert subprocess.run(['pgrep', '-f', '^([^ ]*/)?dbtest_integrated( |$)'], capture_output=True).returncode == 1, 'Leftover Silo'
    print('FINISHED', phase, time.time(), flush=True)
    if phase == 'A':
        a = load_run(output / 'results.json')
        reference = stable_mean_reference(a)
        early = initial_mean_reference(a)
        print('FIXED A STABLE MEANS', reference, flush=True)
        # Do not spend model calls on an obviously growing, overloaded baseline queue.
        stable = [w for w in a['windows'] if w['phase'] == 'stable']
        late = mean(w['values']['silo'] for w in stable)
        if late > early['silo'] * 2:
            raise RuntimeError('A late latency exceeds 2x initial reference: retain A and calibrate load before paid tuning')

manifest = dict(pairs=[dict(id='silo-sysbench-02', a=str(BASE / 'A/results.json'), c=str(BASE / 'C/results.json'),
                           reference_policy='stable_mean')])
save(BASE / 'pairs.json', manifest)
export(None, BASE / 'comparison', plots=True, telemetry=True, pairs_manifest=BASE / 'pairs.json')
status = json.loads((BASE / 'experiment-status.json').read_text())
status.update(completed=True, finished=time.time(), a=str(BASE / 'A/results.json'), c=str(BASE / 'C/results.json'))
save(BASE / 'experiment-status.json', status)
print('EXPERIMENT COMPLETE', flush=True)
