"""Prepared pure unit tests. NOT executed; run only after explicit user authorization."""
from pathlib import Path
import tempfile
import unittest
from .controls import Actuator, Control, decode
from .model import Application


class ExtensionTests(unittest.TestCase):
    def test_baseline_bounds_and_direction(self):
        latency = Application.load(dict(id='A', metric='p99', objective='minimize', start=['server'], measure=['reader']))
        latency.set_baseline([5, 4, 100])
        self.assertEqual(latency.baseline, 5)
        self.assertEqual(latency.observation(4, .05)['improvement'], 1.25)
        self.assertTrue(latency.observation(5.1, .05)['constraint_violation'])
        self.assertFalse(latency.observation(5.1, .05)['significant_regression'])
        throughput = Application.load(dict(id='B', metric='throughput', objective='maximize', start=['server'], measure=['reader'], bound=80, priority=2))
        throughput.set_baseline([100, 100, 100])
        observation = throughput.observation(90, .05)
        self.assertFalse(observation['constraint_violation'])
        self.assertTrue(observation['significant_regression'])
        for invalid in (None, 0, -1, float('nan'), True):
            with self.assertRaises(ValueError):
                throughput.observation(invalid, .05)

    def test_scope_validation_readback_and_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'weight'
            path.write_text('100\n')
            actuator = Actuator({'A': {'cpu.weight': Control(path, 1, 10000)}})
            for bad in ({'application_updates': {'B': {'cpu.weight': 2}}},
                        {'host_updates': {'latency_ns': 2}},
                        {'application_updates': {'A': {'cpu.weight': True}}},
                        {'application_updates': {'A': {'../../x': 3}}},
                        {'commands': ['echo nope']}):
                with self.assertRaises(ValueError):
                    actuator.apply(bad)
            actuator.apply({'application_updates': {'A': {'cpu.weight': 200}}, 'host_updates': {}})
            self.assertEqual(path.read_text().strip(), '200')
            self.assertEqual(actuator.restore(), [])
            self.assertEqual(path.read_text().strip(), '100')

    def test_partial_failure_rolls_back(self):
        class FailOnce(Control):
            def write(self, value):
                if value == '200':
                    raise OSError('simulated failure')
                super().write(value)
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ('a', 'b')]
            for path in paths:
                path.write_text('100\n')
            actuator = Actuator({'A': {'cpu.weight': Control(paths[0], 1, 10000)},
                                 'B': {'cpu.weight': FailOnce(paths[1], 1, 10000)}})
            with self.assertRaises(OSError):
                actuator.apply({'application_updates': {'A': {'cpu.weight': 200}, 'B': {'cpu.weight': 200}}})
            self.assertEqual([p.read_text().strip() for p in paths], ['100', '100'])

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValueError):
            decode('{"host_updates": {}, "host_updates": {}}')

    def test_cpu_quota(self):
        control = Control('/not-used', 10000, 102400000, 'cpu.max')
        self.assertEqual(control.validate('max 100000'), 'max 100000')
        self.assertEqual(control.validate('50000 100000'), '50000 100000')
        for invalid in ('1 100000', 'max', 'max 1000', '10000 100000 extra', 10000):
            with self.assertRaises(ValueError):
                control.validate(invalid)

    def test_shared_window_runs_once(self):
        from concurrent.futures import ThreadPoolExecutor
        from .telemetry import WindowBroker
        class Collector:
            calls = 0
            def collect(self, number, duration):
                self.calls += 1
                return {'window': number}
        collector = Collector()
        broker = WindowBroker(collector, 2, 5)
        broker.tuning_windows = 2
        with ThreadPoolExecutor(max_workers=2) as pool:
            for number in (1, 2, 3):
                futures = [pool.submit(broker.get, number, 10) for _ in range(2)]
                self.assertEqual([f.result() for f in futures], [{'window': number}] * 2)
        self.assertEqual(collector.calls, 3)

    def test_host_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            lo, hi = Path(directory) / 'min', Path(directory) / 'max'
            lo.write_text('10\n')
            hi.write_text('100\n')
            actuator = Actuator({}, {'min_perf_pct': Control(lo, 0, 100), 'max_perf_pct': Control(hi, 1, 100)})
            with self.assertRaises(ValueError):
                actuator.apply({'host_updates': {'min_perf_pct': 90, 'max_perf_pct': 80}})
            actuator.apply({'host_updates': {'min_perf_pct': 20, 'max_perf_pct': 80}})
            self.assertEqual(actuator.restore(), [])

    def test_private_view_contains_no_other_objective(self):
        from .telemetry import View
        class Broker:
            def get(self, number, duration):
                return dict(window=number, phase='tuning', start=1, end=2,
                            applications={'A': {'current': 4}, 'B': {'secret': 100}}, shared={'secret_host': 1})
        app = Application('A', 'p99', 'minimize', ['server'], ['reader'])
        view = View(Broker(), [app], False)
        observation = view.execute_window(window_number=1, duration=1).extra_metrics['extension_observation']
        self.assertEqual(set(observation['applications']), {'A'})
        self.assertNotIn('shared', observation)


if __name__ == '__main__':
    unittest.main()
