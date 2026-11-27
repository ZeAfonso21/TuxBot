"""Foreground installation check; no tuner, host writes or workload cgroups."""
import json
import logging
import os
from pathlib import Path
import signal
import socket
from statistics import mean
import subprocess
import sys
import time
from optimizer.config import SimpleConfig
from optimizer.benchmarks.tailbench import TailbenchBenchmark
from extension.model import Application
from extension.runner import save
from extension.telemetry import Windows

assert socket.gethostname() == 'bart'
logging.basicConfig(level=logging.INFO)
root = Path('results/silo-sysbench-01/install/smoke-01').resolve()
root.mkdir(parents=True, exist_ok=False)
silo = dict(benchmark='tailbench', tailbench_app='silo', tailbench_root='/work_dir/tailbench-src/tailbench',
            tailbench_output_dir=str(root / 'silo'), results_dir=str(root / 'silo-collector'),
            tailbench_qps=1000, tailbench_threads=4, tailbench_silo_scale_factor=4,
            tailbench_warmupreqs=1000, tailbench_maxreqs=1000000000, tailbench_metrics_interval_sec=1)
cpu = dict(workload='cpu', threads=4, cpu_max_prime=50000, metrics_file=str(root / 'cpu.intervals.jsonl'))
save(root / 'silo.json', silo)
save(root / 'cpu.json', cpu)
apps = [Application.load(dict(id='silo', metric='latency_p99', objective='minimize',
            start=[sys.executable, '-m', 'extension.tailbench', 'serve', str(root / 'silo.json')],
            measure=[sys.executable, '-m', 'extension.tailbench', 'measure', str(root / 'silo.json')])),
        Application.load(dict(id='sysbench_cpu', metric='events_per_second', objective='maximize',
            start=[sys.executable, '-m', 'extension.sysbench', 'serve', str(root / 'cpu.json')],
            measure=[sys.executable, '-m', 'extension.sysbench', 'measure', str(root / 'cpu.json')]))]
benchmark = TailbenchBenchmark(SimpleConfig(**silo))
process = None
report = dict(completed=False, scope='installation/concurrent metrics smoke only, NOT 30/20 evaluation',
              silo=silo, sysbench=cpu, started=time.time())
collector = SimpleConfig()
collector.results_dir = str(root / 'telemetry')
collector.optimization_metric = 'instructions_per_cycle'
windows = Windows(collector, apps, None, root, .05)
try:
    with (root / 'sysbench.log').open('w') as log:
        process = subprocess.Popen(apps[1].start, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        assert benchmark.pre_execute(), 'Silo failed startup'
        deadline = time.monotonic() + 180
        while len(list((root / 'silo').glob('lats_interval_*.csv'))) < 3:
            assert benchmark.benchmark_process.poll() is None and process.poll() is None, 'Workload exited'
            assert time.monotonic() < deadline, 'Silo did not emit interval metrics'
            time.sleep(1)
        windows.processes = [benchmark.benchmark_process, process]
        time.sleep(10)
        for number in range(1, 4):
            row = windows.collect(number, 8)
            print('SMOKE WINDOW', number, {a: v['current'] for a, v in row['applications'].items()}, flush=True)
        report['three_window_arithmetic_means'] = {a.id: mean(w['applications'][a.id]['current'] for w in windows.rows) for a in apps}
        report['completed'] = True
except BaseException as exc:
    report['error'] = repr(exc)
    raise
finally:
    benchmark.cleanup()
    if process:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    report.update(windows=windows.rows, finished=time.time())
    save(root / 'results.json', report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('windows', 'silo', 'sysbench')}, indent=2), flush=True)
