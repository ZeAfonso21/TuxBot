"""One co-located window, projected into private single-app or coordinated observations."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import time
import threading
from optimizer.benchmark import BenchmarkInterface, BenchmarkMetrics
from .controls import decode
from .model import positive


def cgroup_sample(path):
    result = {}
    for name in ('cpu.stat', 'cpu.pressure', 'memory.current', 'memory.events', 'memory.pressure', 'io.stat', 'io.pressure'):
        file = path / name
        if file.is_file():
            result[name] = file.read_text().strip()
    return result


class Windows(BenchmarkInterface):
    """Reuse TuxBot's perf/system collectors; measurement commands share explicit endpoints."""
    def __init__(self, config, apps, groups, output, tolerance):
        super().__init__(config)
        self.apps, self.groups = apps, groups
        self.output, self.tolerance = Path(output), tolerance
        self.rows = []
        self.phase = 'baseline'
        self.processes = []
        self.actuator = None
        self.host_observers = {}

    def pre_execute(self):
        return True

    def parse_results(self, output_dir):
        raise NotImplementedError("Metrics come from window measurement commands")

    def execute_window(self, number, duration):
        return self.collect(number, duration)

    def collect(self, number, duration):
        if any(p.poll() is not None for p in self.processes):
            raise RuntimeError("A workload exited before measurement")
        start = time.time()
        before = {a.id: cgroup_sample(self.groups.paths[a.id]) for a in self.apps}
        configuration_start = self.actuator.snapshot() if self.actuator else None
        host_start = {k: c.read() for k, c in self.host_observers.items()}
        # A unique collector index avoids overwriting baseline/stable artifacts.
        index = len(self.rows)
        perf = self.collect_perf_metrics(index, duration)
        self.start_system_measurement(index, duration)
        try:
            time.sleep(duration)
            end = time.time()
            after = {a.id: cgroup_sample(self.groups.paths[a.id]) for a in self.apps}
        finally:
            self.finalize_perf_metrics(index, perf)

        def measure(app):
            # Adapters MUST select completed observations in this exact [start,end) interval.
            import os
            env = dict(os.environ, TUXBOT_WINDOW_START=str(start), TUXBOT_WINDOW_END=str(end),
                       TUXBOT_APPLICATION_ID=app.id, TUXBOT_WINDOW_PHASE=self.phase)
            completed = subprocess.run(app.measure, env=env, capture_output=True, text=True,
                                       check=True, timeout=max(30, duration * 2))
            data = decode(completed.stdout)
            if not isinstance(data, dict) or app.metric not in data:
                raise ValueError(f"Missing {app.id}/{app.metric}")
            if data.get('window_start') != start or data.get('window_end') != end:
                raise ValueError("Measurement adapter must echo exact window endpoints")
            positive(data[app.metric])
            return data

        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(measure, self.apps))
        if any(p.poll() is not None for p in self.processes):
            raise RuntimeError("A workload exited during measurement")
        metrics = BenchmarkMetrics()
        self._populate_system_metrics(metrics, index, start, end)
        system = dict(metrics.extra_metrics)
        for name in ('power_socket0_watts', 'power_ram_watts', 'cpu_load_cores_pct', 'cpu_load_socket0_pct'):
            system[name] = getattr(metrics, name)
        observations = {}
        for app, raw in zip(self.apps, values):
            value = raw[app.metric]
            observation = app.observation(value, self.tolerance) if app.baseline else dict(metric=app.metric, objective=app.objective, current=value)
            observation.update(raw=raw, cgroup_before=before[app.id], cgroup_after=after[app.id])
            observations[app.id] = observation
        row = dict(window=number, phase=self.phase, start=start, end=end, applications=observations,
                   shared=system, configuration_start=configuration_start,
                   configuration_end=self.actuator.snapshot() if self.actuator else None,
                   observed_host_start=host_start,
                   observed_host_end={k: c.read() for k, c in self.host_observers.items()})
        self.rows.append(row)
        return row


class WindowBroker:
    """Two independent controllers rendezvous; only one measurement is performed per window."""
    def __init__(self, windows, parties, timeout):
        self.windows, self.timeout = windows, timeout
        self.lock = threading.Lock()
        self.requests = []
        self.result = None
        self.error = None
        self.barrier = threading.Barrier(parties, action=self._collect, timeout=timeout)
        self.release = threading.Barrier(parties, timeout=timeout)

    def _collect(self):
        try:
            if len(set(self.requests)) != 1:
                raise RuntimeError("Independent controllers requested different windows")
            number, duration = self.requests[0]
            self.windows.phase = 'stable' if number > self.tuning_windows else 'tuning'
            self.result = self.windows.collect(number, duration)
        except BaseException as exc:
            self.error = exc
        finally:
            self.requests.clear()

    def get(self, number, duration):
        with self.lock:
            self.requests.append((number, duration))
        self.barrier.wait()
        if self.error:
            raise RuntimeError("Synchronized window failed") from self.error
        result = self.result
        self.release.wait()  # no caller can overwrite result until both have copied it
        return result

    def abort(self):
        self.barrier.abort()
        self.release.abort()


class View:
    """No other application or shared-host telemetry crosses the independent boundary."""
    def __init__(self, broker, apps, coordinated):
        self.broker, self.apps, self.coordinated = broker, apps, coordinated
        self.latest = None

    def pre_execute(self):
        return True

    def cleanup(self):
        pass  # runner owns both workloads and their joint lifecycle

    def update_workload(self, iteration):
        pass

    def execute_window(self, window_number, duration):
        row = self.broker.get(window_number, duration)
        self.latest = dict(window=row['window'], phase=row['phase'], start=row['start'], end=row['end'],
                           applications={a.id: row['applications'][a.id] for a in self.apps})
        if self.coordinated:
            self.latest['shared'] = row['shared']
        # Scalar reward is only for compatibility with the original scheduler/history;
        # the LLM sees raw per-app objectives, never a substitute mathematical optimizer.
        return BenchmarkMetrics(extra_metrics={'extension_observation': self.latest, 'extension_reward': 1.0})
