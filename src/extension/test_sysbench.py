"""Pure tests for continuous workload metrics, cgroup rates and pilot bounds."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from .controls import Control
from .host import limit_host
from .sysbench import command, measure, parse_interval
from .telemetry import cgroup_deltas


class SysbenchTests(unittest.TestCase):
    def test_real_collector_is_concrete(self):
        from optimizer.config import SimpleConfig
        from .telemetry import Windows
        with tempfile.TemporaryDirectory() as directory:
            config = SimpleConfig()
            config.results_dir = directory
            with patch('optimizer.benchmark.get_repo_root', return_value=directory):
                collector = Windows(config, [], None, directory, .05)
            collector.cleanup()
            self.assertEqual(collector.rows, [])

    def test_report_parsing(self):
        self.assertEqual(parse_interval('[ 2s ] thds: 4 eps: 1185.43 lat (ms,99%): 3.75', 'cpu'),
                         dict(elapsed=2, events_per_second=1185.43, latency_p99_ms=3.75))
        self.assertEqual(parse_interval('[ 1s ] 21455.58 MiB/sec', 'memory'),
                         dict(elapsed=1, throughput_mib_s=21455.58))
        self.assertIsNone(parse_interval('Latency (ms):', 'cpu'))
        self.assertIn('--memory-block-size=256M', command({'workload': 'memory'}))

    def test_contained_intervals_and_percentile_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cpu.jsonl'
            rows = [dict(start=i, end=i + 1, latency_p99_ms=3 + i, events_per_second=100) for i in range(6)]
            path.write_text(''.join(json.dumps(r) + '\n' for r in rows) + '{"partial":')
            result = measure({'metrics_file': str(path), 'workload': 'cpu'}, 1.1, 5.5)
            self.assertEqual(result['intervals'], 3)
            self.assertEqual(result['latency_p99_ms'], 7)
            self.assertEqual(result['events_per_second'], 100)
            self.assertIn('NOT pooled', result['percentile_semantics'])
            with self.assertRaises(ValueError):
                measure({'metrics_file': str(path), 'workload': 'cpu'}, 20, 28)

    def test_memory_mean(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'memory.jsonl'
            path.write_text(''.join(json.dumps(dict(start=i, end=i + 1, throughput_mib_s=100 * (i + 1))) + '\n' for i in range(3)))
            self.assertEqual(measure({'metrics_file': str(path), 'workload': 'memory'}, 0, 3)['throughput_mib_s'], 200)

    def test_cgroup_rates_and_missing(self):
        before = {'cpu.stat': 'usage_usec 1000000\nnr_throttled 1\nthrottled_usec 100\n',
                  'cpu.pressure': 'some avg10=0.0 total=200000\n'}
        after = {'cpu.stat': 'usage_usec 5000000\nnr_throttled 3\nthrottled_usec 2000100\n',
                 'memory.current': '1073741824', 'cpu.pressure': 'some avg10=1.0 total=1200000\n'}
        result = cgroup_deltas(before, after, 2)
        self.assertEqual(result['cpu_usage_cores'], 2)
        self.assertEqual(result['cpu_throttled_seconds'], 2)
        self.assertEqual(result['cpu_throttled_periods'], 2)
        self.assertEqual(result['cpu_pressure_some_seconds'], 1)
        self.assertEqual(cgroup_deltas({}, {}, 2), {})

    def test_pilot_refuses_wrong_host_before_io(self):
        from .pilot import execute
        with patch('extension.pilot.socket.gethostname', return_value='not-bart'):
            with self.assertRaisesRegex(RuntimeError, 'Wrong hostname'):
                execute('/file-that-must-not-be-read', 'bart')

    def test_host_ranges_can_only_narrow(self):
        control = Control('/not-used', 0, 100)
        limit_host({'min_perf_pct': control}, {'min_perf_pct': [45, 100]})
        self.assertEqual(control.minimum, 45)
        with self.assertRaises(ValueError):
            limit_host({'min_perf_pct': control}, {'other': [0, 10]})
        with self.assertRaises(ValueError):
            limit_host({'min_perf_pct': control}, {'min_perf_pct': [120, 200]})


if __name__ == '__main__':
    unittest.main()
