"""Explicitly gated experiment entry point. Do not invoke on a development host."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

from .controls import Actuator, Cgroups, cgroup_controls, decode
from .model import Application


def save(path, data):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, indent=2, allow_nan=False, default=str) + '\n')
    temp.replace(path)


def child_exec(group, command):
    # Executed in a fresh interpreter before exec, not unsafe preexec_fn in threaded parent.
    (Path(group) / 'cgroup.procs').write_text(str(os.getpid()))
    os.execvp(command[0], command)


def baseline_membership(apps, processes):
    """Verify the untuned launch inherited its cgroup without writing membership."""
    inherited = Path('/proc/self/cgroup').read_text()
    memberships = {a.id: Path(f'/proc/{p.pid}/cgroup').read_text() for a, p in zip(apps, processes)}
    if any(value != inherited for value in memberships.values()):
        raise RuntimeError('A workload did not inherit baseline cgroup membership')
    return dict(inherited_cgroup=inherited, workload_cgroup_membership=memberships)


def run(data):
    from optimizer.config import SimpleConfig
    from .host import resolve_host, limit_host
    from .telemetry import Windows, WindowBroker, View
    mode = data['mode']
    if mode not in ('default', 'independent', 'coordinated'):
        raise ValueError('Unknown experiment mode')
    if mode == 'default' and data.get('cgroup_root'):
        raise ValueError('No-cgroup A requires omitting cgroup_root from its configuration')
    if data.get('defaults_verified') is not True:
        raise ValueError('Operator must verify default kernel/ancestor settings and set defaults_verified=true')
    apps = [Application.load(a) for a in data['applications']]
    if len(apps) != 2 or len({a.id for a in apps}) != 2:
        raise ValueError('Exactly two distinct applications are required')
    duration = data.get('window_seconds', 10)
    tuning = data.get('tuning_windows', 10)
    stable = data.get('stable_windows', 3)
    warmup = data.get('warmup_seconds', 30)
    if any(type(x) is not int or x < 1 for x in (duration, tuning, stable)) or type(warmup) is not int or warmup < 0:
        raise ValueError('Invalid phase durations/counts')
    tolerance = data.get('regression_tolerance', 0.05)
    sustained = data.get('regression_windows', 3)
    if type(tolerance) not in (int, float) or not 0 <= tolerance < 1 or type(sustained) is not int or sustained < 2:
        raise ValueError('Invalid regression policy')
    if mode != 'default' and not os.getenv('GEMINI_API_KEY'):
        raise ValueError('Future tuning execution requires GEMINI_API_KEY; no workload has been started')
    output = Path(data['results_dir']).resolve()
    output.mkdir(parents=True, exist_ok=False)  # never mix/overwrite experimental runs
    # EXTENSION: A inherits the caller's cgroup; only B/C create workload groups.
    groups = Cgroups(data['cgroup_root'], [a.id for a in apps]) if mode != 'default' else None
    controllers, processes, logs = [], [], []
    windows, master = None, None
    result = dict(mode=mode, config=data, completed=False,
                  provenance=dict(dedicated_workload_cgroups=groups is not None, concurrent_workloads=True),
                  data_kind=data.get('data_kind', 'measured'))
    try:
        if groups is not None:
            groups.create()
            result['cgroup_parent_initial_controllers'] = groups.original_subtree
            save(output / 'cgroup_state.json', dict(root=str(groups.root), initial_controllers=groups.original_subtree))
        host, report = resolve_host(data.get('approved_host_parameters', []))
        limit_host(host, data.get('host_limits', {}))
        save(output / 'host_compatibility.json', report)
        if mode == 'coordinated' and not host:
            raise RuntimeError('Coordinated experiments require at least one verified writable host control')
        controls = {a.id: cgroup_controls(groups.paths[a.id], data.get('cgroup_policy', {}).get(a.id, {})) for a in apps} if groups is not None else {}
        master = Actuator(controls, host if mode == 'coordinated' else {})
        result['initial_configuration'] = master.initial
        result['initial_host_observations'] = {k: c.read() for k, c in host.items()}
        save(output / 'initial_state.json', result)
        collector_config = SimpleConfig()
        collector_config.results_dir = str(output / 'telemetry')
        if data.get('require_perf_metrics', False):
            collector_config.optimization_metric = 'instructions_per_cycle'
        windows = Windows(collector_config, apps, groups, output, tolerance)
        windows.actuator = master
        windows.host_observers = host
        windows.processes = processes
        for app in apps:
            log = (output / f'{app.id}.log').open('w')
            logs.append(log)
            command = [sys.executable, '-m', 'extension.runner', '--child', str(groups.paths[app.id]), *app.start] if groups is not None else app.start
            env = dict(os.environ, TUXBOT_READY_FILE=str(output / f'{app.id}.ready'))
            processes.append(subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, env=env))
        deadline = time.monotonic() + data.get('startup_timeout_seconds', 300)
        while any(a.ready_signal and not (output / f'{a.id}.ready').is_file() for a in apps):
            if any(p.poll() is not None for p in processes) or time.monotonic() > deadline:
                raise RuntimeError('Workload readiness failed or timed out')
            time.sleep(0.1)
        if groups is None:
            # EXTENSION: record and verify inherited membership; no cgroup write in A.
            result.update(baseline_membership(apps, processes))
        time.sleep(warmup)
        baseline = [windows.collect(-i, duration) for i in range(1, 4)]
        for app in apps:
            app.set_baseline([row['applications'][app.id]['current'] for row in baseline])
        baseline_context = {a.id: a.observation(a.baseline, tolerance) for a in apps}
        result['applications'] = [asdict(a) for a in apps]
        save(output / 'baseline.json', dict(applications=baseline_context, windows=baseline,
                                          aggregation='median of three window metrics, NOT pooled request p99'))
        if mode == 'default':
            for phase, count in (('tuning', tuning), ('stable', stable)):
                windows.phase = phase
                for number in range(1, count + 1):
                    windows.collect(number if phase == 'tuning' else tuning + number, duration)
        else:
            from .controller import ScopedController, ScopedTuner
            selections = [apps] if mode == 'coordinated' else [[a] for a in apps]
            broker = WindowBroker(windows, len(selections), data.get('synchronization_timeout_seconds', 3600))
            broker.tuning_windows = tuning
            decisions = {}
            result['decisions'] = decisions
            for selected in selections:
                label = 'coordinated' if mode == 'coordinated' else selected[0].id
                manager = master if mode == 'coordinated' else Actuator({a.id: controls[a.id] for a in selected})
                runtime = SimpleNamespace(manager=manager, tuner_class=ScopedTuner, coordinated=mode == 'coordinated',
                                          baseline={'applications': {a.id: baseline_context[a.id] for a in selected}},
                                          decisions=[], bad_windows=0, regression_windows=sustained)
                config = SimpleConfig()
                config.benchmark = 'extension'
                config.parameter_ranges, config.fixed_parameters = {}, {}
                config.parameters_to_tune = None
                config.optimization_metric, config.optimization_goal = 'extension_reward', 'maximize'
                config.max_iterations, config.post_tuning_windows = tuning, stable
                config.window_duration = duration
                # Keep settings narrow: no legacy profiles, trimming, replay, fixed knobs, or gists.
                config.llm_actor_model = data.get('actor_model', 'gemini-3.5-flash')
                config.llm_speculator_model = data.get('instant_model', 'gemini-3.5-flash-lite')
                if not all(m.startswith('gemini-') for m in (config.llm_actor_model, config.llm_speculator_model)):
                    raise ValueError('Initial extension runner supports Gemini models only')
                config.llm_request_timeout_seconds = data.get('llm_timeout_seconds', 120)
                config.llm_request_max_retries = 3
                config.tuning_mode = 'outside-of-window'
                config.dual_loop_force_final_actor_before_stable = True
                config.results_dir = str(output / label)
                Path(config.results_dir).mkdir()
                config._extension_runtime = runtime
                decisions[label] = runtime.decisions
                controllers.append(ScopedController(config, View(broker, selected, mode == 'coordinated')))
            with ThreadPoolExecutor(max_workers=len(controllers)) as pool:
                try:
                    results = list(pool.map(lambda c: c.run(), controllers))
                except BaseException:
                    broker.abort()
                    for controller in controllers:
                        controller.running = False
                    raise
            result['controllers'] = results
            result['decisions'] = decisions
            if any(r['terminated_reason'] != 'completed' for r in results):
                raise RuntimeError('At least one tuner did not complete')
        result['completed'] = True
    except BaseException as exc:
        result['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        errors = []
        # Kill all descendants in our freshly created groups (not just original leaders).
        for group in groups.created if groups is not None else []:
            try:
                kill = group / 'cgroup.kill'
                if kill.is_file():
                    kill.write_text('1')
                elif (group / 'cgroup.procs').read_text().strip():
                    errors.append(f'{group}: cgroup.kill unavailable; inspect descendants manually')
            except OSError as exc:
                errors.append(str(exc))
        for process in processes:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired as exc:
                errors.append(str(exc))
        for log in logs:
            log.close()
        if groups is not None:
            try:
                errors.extend(groups.await_empty())
            except OSError as exc:
                errors.append(f'Could not verify empty cgroups: {exc}')
        result['scoped_actuation_audits'] = {
            str(i): c.param_manager.audit for i, c in enumerate(controllers)
        }
        if any(c.param_manager.poisoned for c in controllers):
            result['completed'] = False
            errors.append('A scoped actuator failed rollback during tuning')
        if master:
            try:
                errors.extend(master.restore())
                result['effective_after_restore'] = master.snapshot()
            except Exception as exc:
                errors.append(f'Restoration/readback failed: {exc}')
            result['actuation_audit'] = master.audit
        if windows:
            result['windows'] = windows.rows
        result['cgroup_parent_initial_controllers'] = groups.original_subtree if groups is not None else None
        if groups is not None:
            errors.extend(groups.cleanup())
        result['restoration_errors'] = errors
        if errors:
            result['completed'] = False
        save(output / 'results.json', result)
        if errors:
            raise RuntimeError(f'Restoration incomplete: {errors}; see {output}/results.json')


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--child':
        child_exec(sys.argv[2], sys.argv[3:])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config')
    parser.add_argument('--authorize-execution', action='store_true', help='Allows real workloads, cgroups, kernel writes, and paid API requests')
    args = parser.parse_args()
    if not args.authorize_execution:
        parser.error('Execution disabled: explicit --authorize-execution required on a dedicated machine')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    data = decode(Path(args.config).read_text())
    # Catch graceful interruption; SIGKILL/power loss still require the saved snapshot.
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f'signal {signum}')
    signal.signal(signal.SIGTERM, interrupted)
    run(data)


if __name__ == '__main__':
    main()
