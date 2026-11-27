"""Small regressions for common initial-mean references and native-child cleanup."""
import json
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from .baseline import initial_mean_reference, load_reference
from .evaluation import evaluate_pair, load_run
from .evaluation_fixture import fixture_runs
from .model import Application


class SharedBaselineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.a, self.c = fixture_runs()
        for row, value in zip(self.a['windows'][:3], (1, 2, 12)):
            row['applications']['cpu_latency']['current'] = value

    def save(self, name, data):
        path = self.root / name
        path.write_text(json.dumps(data))
        return path

    def test_initial_mean_is_not_initial_or_stable_median(self):
        a = load_run(self.save('A.json', self.a))
        self.assertEqual(initial_mean_reference(a)['cpu_latency'], 5)
        app = Application.load(dict(id='cpu_latency', metric='latency_p99_ms', objective='minimize', start=['fake'], measure=['fake']))
        app.set_baseline([1, 2, 12], 'mean')
        self.assertEqual(app.baseline, 5)
        with self.assertRaises(ValueError):
            app.set_baseline([1, 2, 12], 'unknown')

    def test_loader_checks_identity_and_completed_no_cgroup_A(self):
        apps = [Application.load(dict(id=a['id'], metric=a['metric'], objective=a['objective'], start=['fake'], measure=['fake'])) for a in self.a['applications']]
        conditions = self.a['config']['workload_conditions']
        path = self.save('A.json', self.a)
        reference = load_reference(path, apps, conditions)
        self.assertEqual(reference['values']['cpu_latency'], 5)
        with self.assertRaises(ValueError):
            load_reference(path, apps, {'different': {}})
        self.a['completed'] = False
        with self.assertRaises(ValueError):
            load_reference(self.save('A.json', self.a), apps, conditions)

    def test_report_uses_exact_same_reference_and_stable_raw_mean(self):
        a = load_run(self.save('A.json', self.a))
        self.c['baseline_reference'] = dict(sha256=a['sha256'], values=initial_mean_reference(a))
        c = load_run(self.save('C.json', self.c))
        pair = evaluate_pair(a, c, review={'reference_policy': 'initial_mean'})
        self.assertEqual(pair['reference']['cpu_latency'], 5)
        self.assertEqual(evaluate_pair(a, c)['reference']['cpu_latency'], 5)
        with self.assertRaises(ValueError):
            evaluate_pair(a, c, review={'reference_policy': 'stable_median'})
        self.assertEqual(pair['reference_windows'], [-1, -2, -3])
        self.assertAlmostEqual(pair['summary'][0]['coordinated'], (5 + 3.2 + 3) / 3)
        self.c['baseline_reference']['values']['cpu_latency'] = 999
        with self.assertRaises(ValueError):
            evaluate_pair(a, load_run(self.save('C.json', self.c)), review={'reference_policy': 'initial_mean'})

    def test_tailbench_sigterm_runs_native_cleanup(self):
        from .tailbench import bridge
        benchmark = MagicMock()
        benchmark.output_dir = str(self.root)
        benchmark.pre_execute.return_value = True
        previous = signal.getsignal(signal.SIGTERM)
        benchmark.benchmark_process.wait.side_effect = lambda: signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        with patch('optimizer.benchmarks.tailbench.TailbenchBenchmark', return_value=benchmark):
            with self.assertRaises(SystemExit):
                bridge('serve', self.save('config.json', {}))
        benchmark.cleanup.assert_called_once()
        self.assertEqual(signal.getsignal(signal.SIGTERM), previous)
