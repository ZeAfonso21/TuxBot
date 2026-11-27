"""Execution recipe for this batch only; uses the existing extension harness."""
import copy
import json
import os
from pathlib import Path
import signal
import socket
from statistics import median
import subprocess
import sys
import time

from extension.controls import Actuator, Cgroups, cgroup_controls
from extension.host import resolve_host
from extension.model import Application
from extension.pilot import execute
from extension.runner import save
from extension.telemetry import Windows
from optimizer.config import SimpleConfig

BASE = Path('results/relationships-01')
PYTHON = sys.executable
assert socket.gethostname() == 'bart'
TEMPLATE = json.loads(Path('src/extension/examples/pilot-C.json').read_text())
VERSION = subprocess.check_output(['sysbench', '--version'], text=True).strip()
CASES = [
    ('cpu-cpu-frequency', 'aligned', [('prime_10000', 'cpu', 4, 10000, None, 'events_per_second', 'maximize'), ('prime_20000', 'cpu', 4, 20000, None, 'events_per_second', 'maximize')], {'host_updates': {'max_perf_pct': 80}}),
    ('cpu-memory-contention', 'conflicting', [('cpu_latency', 'cpu', 8, 20000, None, 'latency_p99_ms', 'minimize'), ('memory_bandwidth', 'memory', 8, None, None, 'throughput_mib_s', 'maximize')], {'application_updates': {'cpu_latency': {'cpu.weight': 1000}}}),
    ('cpu-memory-partitioned', 'weakly_related', [('cpu_latency', 'cpu', 1, 20000, '0', 'latency_p99_ms', 'minimize'), ('memory_bandwidth', 'memory', 1, None, '2', 'throughput_mib_s', 'maximize')], {'application_updates': {'cpu_latency': {'cpu.max': '50000 100000'}}}),
]


def profile(case, phase, definitions):
    output = BASE / case / phase
    config = copy.deepcopy(TEMPLATE)
    config.update(results_dir=str(output), mode='default' if phase == 'A' else 'coordinated',
                  defaults_verified=True, tuning_windows=30, stable_windows=20,
                  workload_conditions={}, applications=[])
    if phase == 'A':
        config.pop('cgroup_root', None)
    else:
        config['cgroup_root'] = '/sys/fs/cgroup/tuxbot-rel01-' + case + '-' + phase
    for app, workload, threads, prime, affinity, metric, objective in definitions:
        workload_config = dict(workload=workload, threads=threads, metrics_file=str(output / (app + '.intervals.jsonl')))
        condition = dict(program='sysbench', version=VERSION, workload=workload, threads=threads,
                         rand_seed=1, report_interval_seconds=1, cpu_affinity=affinity)
        if workload == 'cpu':
            workload_config['cpu_max_prime'] = prime
            condition['cpu_max_prime'] = prime
        else:
            condition.update(memory_block_size='256M', memory_scope='local', memory_oper='read', memory_access_mode='seq')
        filename = BASE / 'configs' / (case + '-' + phase + '-' + app + '.json')
        save(filename, workload_config)
        start = [PYTHON, '-m', 'extension.sysbench', 'serve', str(filename)]
        if affinity:
            start = ['taskset', '-c', affinity, *start]
        config['applications'].append(dict(id=app, metric=metric, objective=objective, bound='default', priority=1,
                                           ready_signal=True, start=start,
                                           measure=[PYTHON, '-m', 'extension.sysbench', 'measure', str(filename)]))
        config['workload_conditions'][app] = condition
    filename = BASE / 'configs' / (case + '-' + phase + '.json')
    save(filename, config)
    return config, filename


def screen(case, definitions, intervention):
    config, _ = profile(case, 'screen', definitions)
    output = Path(config['results_dir'])
    output.mkdir(parents=True, exist_ok=False)
    parent = Path('/sys/fs/cgroup/cgroup.subtree_control')
    before = parent.read_text().split()
    root = Path(config['cgroup_root'])
    assert not root.exists()
    host, _ = resolve_host(config['approved_host_parameters'])
    initial = {k: v.read() for k, v in host.items()}
    assert initial == {k: str(v) for k, v in config['expected_initial_host'].items()}, initial
    apps = [Application.load(a) for a in config['applications']]
    groups = Cgroups(root, [a.id for a in apps])
    processes, logs, errors = [], [], []
    master = windows = None
    report = dict(case=case, config=config, intervention=intervention, initial_host=initial, completed=False,
                  classification_note='Control- and load-specific descriptive screen, not an intrinsic app label or statistical significance claim')
    try:
        if 'cpu' not in before:
            parent.write_text('+cpu')
        root.mkdir()
        groups.create()
        master = Actuator({a.id: cgroup_controls(groups.paths[a.id], {}) for a in apps}, host)
        collector = SimpleConfig()
        collector.results_dir = str(output / 'telemetry')
        collector.optimization_metric = 'instructions_per_cycle'
        windows = Windows(collector, apps, groups, output, .05)
        windows.actuator, windows.host_observers, windows.processes = master, host, processes
        for app in apps:
            log = (output / (app.id + '.log')).open('w')
            logs.append(log)
            processes.append(subprocess.Popen([PYTHON, '-m', 'extension.runner', '--child', str(groups.paths[app.id]), *app.start],
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                env=dict(os.environ, TUXBOT_READY_FILE=str(output / (app.id + '.ready')))))
        deadline = time.monotonic() + 60
        while not all((output / (a.id + '.ready')).exists() for a in apps):
            assert all(p.poll() is None for p in processes) and time.monotonic() < deadline, 'Readiness failed'
            time.sleep(.1)
        time.sleep(10)
        number = 0
        for cycle in range(2):
            for phase in ('before', 'intervention', 'after'):
                assert not master.restore(), 'Screen reset failed'
                if phase == 'intervention':
                    master.apply(intervention)
                time.sleep(3)
                windows.phase = str(cycle) + '-' + phase
                for _ in range(3):
                    number += 1
                    windows.collect(number, 8)
                    save(output / 'progress.json', dict(last_window=number, phase=windows.phase))
        report['completed'] = True
    finally:
        for group in groups.created:
            (group / 'cgroup.kill').write_text('1')
        for p in processes:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.wait(timeout=10)
        for log in logs:
            log.close()
        errors += groups.await_empty()
        if master:
            errors += master.restore()
            report['actuation_audit'] = master.audit
        errors += groups.cleanup()
        if root.exists():
            root.rmdir()
        if 'cpu' not in before and 'cpu' in parent.read_text().split():
            parent.write_text('-cpu')
        report.update(windows=windows.rows if windows else [], restoration_errors=errors,
                      host_after={k: v.read() for k, v in host.items()}, parent_before=before, parent_after=parent.read_text().split())
        save(output / 'results.json', report)
        assert not errors and report['host_after'] == initial and set(report['parent_after']) == set(before), 'Screen restoration failed'
    effects = []
    for cycle in range(2):
        effect = {}
        for app in apps:
            samples = {phase: [r['applications'][app.id]['current'] for r in windows.rows if r['phase'] == str(cycle) + '-' + phase]
                       for phase in ('before', 'intervention', 'after')}
            reference = median(samples['before'] + samples['after'])
            changed = median(samples['intervention'])
            sign = -1 if app.objective == 'minimize' else 1
            effect[app.id] = dict(reference=reference, intervention=changed,
                improvement_pct=sign * 100 * (changed - reference) / reference,
                reference_drift_pct=100 * (median(samples['after']) - median(samples['before'])) / median(samples['before']))
        effects.append(effect)
    return effects


def qualifies(relationship, effects):
    for cycle in effects:
        left, right = [v['improvement_pct'] for v in cycle.values()]
        if relationship == 'aligned' and not (left * right > 0 and min(abs(left), abs(right)) >= 5):
            return False
        if relationship == 'conflicting' and not (left * right < 0 and min(abs(left), abs(right)) >= 5):
            return False
        if relationship == 'weakly_related' and not (abs(left) >= 10 and abs(right) <= 3):
            return False
    return True


def main():
    (BASE / 'configs').mkdir(parents=True, exist_ok=True)
    summary = dict(started=time.time(), cases={}, scope='Three Sysbench load/affinity regimes; not three distinct benchmark suites',
                   criterion='Two intervention cycles: aligned/conflicting both >=5% with same/opposite signs; weak CPU >=10%, memory <=3%. Descriptive only.')
    save(BASE / 'batch-status.json', summary)
    for case, relationship, definitions, intervention in CASES:
        print('SCREEN', case, flush=True)
        effects = screen(case, definitions, intervention)
        summary['cases'][case] = dict(hypothesis=relationship, effects=effects, qualified=qualifies(relationship, effects))
        save(BASE / 'batch-status.json', summary)
        print(json.dumps(summary['cases'][case]), flush=True)
    if not all(v['qualified'] for v in summary['cases'].values()):
        raise RuntimeError('A relationship did not qualify; retain raw results, do not force labels')
    for case, relationship, definitions, intervention in CASES:
        for phase in ('A', 'C'):
            config, filename = profile(case, phase, definitions)
            print('RUN', case, phase, time.time(), flush=True)
            execute(filename, 'bart')
            summary['cases'][case][phase] = str(Path(config['results_dir']) / 'results.json')
            save(BASE / 'batch-status.json', summary)
            print('FINISHED', case, phase, time.time(), flush=True)
        from extension.report import export
        outputs = summary['cases'][case]
        export([outputs['A'], outputs['C']], BASE / case / 'comparison', plots=True, telemetry=True)
    summary['completed'] = True
    summary['finished'] = time.time()
    save(BASE / 'batch-status.json', summary)


if __name__ == '__main__':
    main()
