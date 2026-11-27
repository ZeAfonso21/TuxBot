"""Full 30/20 loop regressions: only temporary controls, fake workloads and mocked SDK."""
from contextlib import ExitStack
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from optimizer.benchmark import BenchmarkMetrics
from optimizer.dual_loop_optimizer import SimpleDualLoopOptimizer
from .controller import ScopedController, ScopedTuner
from .controls import Control
from .runner import run
from .test_runner import FakeGroups, FakeWindows


class SnapshotWindows(FakeWindows):
    def collect(self, number, duration):
        assert duration == 5  # virtual duration only; no sleep or perf subprocess
        configuration = self.actuator.snapshot()
        start = len(self.rows) * duration
        values = {'A': 4, 'B': 100} if self.phase == 'baseline' else {'A': 6, 'B': 120}
        if self.phase != 'baseline' and configuration['application_updates']:
            values = {'A': int(configuration['application_updates']['A']['cpu.weight']) / 100,
                      'B': 120 + int(configuration['application_updates']['B']['cpu.weight']) / 100}
        applications = {}
        for app in self.apps:
            value = values[app.id]
            observation = app.observation(value, self.tolerance) if app.baseline else dict(metric=app.metric, objective=app.objective, current=value)
            observation['raw'] = dict(window_start=start, window_end=start + duration)
            applications[app.id] = observation
        host = {k: v.read() for k, v in self.host_observers.items()}
        row = dict(window=number, phase=self.phase, start=start, end=start + duration,
                   applications=applications, shared={}, configuration_start=configuration,
                   configuration_end=copy.deepcopy(configuration), observed_host_start=host, observed_host_end=host.copy())
        self.rows.append(row)
        return row


class AttributionTests(unittest.TestCase):
    def exercise(self, legacy=False):
        prompts = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            host = root / 'host'
            host.write_text('0\n')

            def host_controls(approved):
                return {'napi_busy_poll': Control(host, 0, 1000)}, {'synthetic': True}

            def group_controls(path, policy):
                return {'cpu.weight': Control(path / 'cpu.weight', 1, 10000)}

            def transport(tuner, contents, *args, **kwargs):
                payload = json.loads(contents[-1])
                prompts.append(payload)
                n = payload['iteration']
                proposal = dict(application_updates={'A': {'cpu.weight': 100 + 10 * n}, 'B': {'cpu.weight': 110 + 10 * n}},
                                host_updates={'napi_busy_poll': n}, reasoning='deterministic mocked update')
                return json.dumps(proposal), proposal, .001, {}, None, {'input_tokens': 1}

            process = MagicMock()
            process.poll.return_value = None
            process.wait.return_value = 0
            process.pid = 999999999
            with ExitStack() as stack:
                stack.enter_context(patch('extension.runner.Cgroups', FakeGroups))
                stack.enter_context(patch('extension.runner.cgroup_controls', group_controls))
                stack.enter_context(patch('extension.host.resolve_host', host_controls))
                stack.enter_context(patch('extension.telemetry.Windows', SnapshotWindows))
                popen = stack.enter_context(patch('extension.runner.subprocess.Popen', return_value=process))
                stack.enter_context(patch('extension.runner.os.killpg'))
                stack.enter_context(patch('extension.runner.baseline_membership', return_value=dict(inherited_cgroup='0::/', workload_cgroup_membership={'A': '0::/', 'B': '0::/'})))
                sdk = stack.enter_context(patch('optimizer.tuners.llm.genai.Client'))
                sdk.return_value.models.generate_content.side_effect = AssertionError('Live API forbidden')
                stack.enter_context(patch.dict('os.environ', {'GEMINI_API_KEY': 'mock-not-a-real-key'}))
                stack.enter_context(patch.object(ScopedTuner, '_call_llm_with_retries', transport))
                if legacy:
                    # Negative control: reproduce the old post-write history labeling, without editing files.
                    stack.enter_context(patch.object(ScopedController, '_record_trial', SimpleDualLoopOptimizer._record_trial))
                base = dict(defaults_verified=True, data_kind='synthetic', warmup_seconds=0,
                            window_seconds=5, tuning_windows=30, stable_windows=20, baseline_aggregation='mean',
                            workload_conditions={'A': {'program': 'SYNTHETIC latency'}, 'B': {'program': 'SYNTHETIC throughput'}},
                            applications=[dict(id='A', metric='latency_p99', objective='minimize', start=['fake'], measure=['fake']),
                                          dict(id='B', metric='events_per_second', objective='maximize', start=['fake'], measure=['fake'])])
                run(dict(base, mode='default', results_dir=str(root / 'A')))
                run(dict(base, mode='coordinated', results_dir=str(root / 'C'), cgroup_root=str(root / 'groups'),
                         reference_run=str(root / 'A/results.json'), reference_policy='stable_mean'))
                self.assertEqual(popen.call_count, 4)
                sdk.return_value.models.generate_content.assert_not_called()
            a = json.loads((root / 'A/results.json').read_text())
            c = json.loads((root / 'C/results.json').read_text())
            history = json.loads(Path(c['controllers'][0]['history_file']).read_text())['history']
            self.assertTrue(a['completed'] and c['completed'])
            self.assertEqual(c['restoration_errors'], [])
            self.assertEqual(c['baseline_reference']['values'], {'A': 6, 'B': 120})
            self.assertEqual(c['baseline_reference']['windows'], list(range(31, 51)))
            self.assertEqual(c['measured_initial_baselines'], {'A': 4, 'B': 100})
            self.assertEqual([app['baseline'] for app in c['applications']], [6, 120])
            seed = history[0]['metrics']['extension_observation']['applications']
            self.assertEqual((seed['A']['current'], seed['A']['bound']), (4, 6))
            self.assertEqual((seed['B']['current'], seed['B']['bound']), (100, 120))
            self.assertEqual(len(c['windows']), 53)
            self.assertEqual(host.read_text().strip(), '0')
            return c, history, prompts

    def test_30_20_history_and_final_prompt_use_measured_not_next_controls(self):
        run_data, history, prompts = self.exercise()
        rows = {w['window']: w for w in run_data['windows'] if w['window'] > 0}
        entries = {e['iteration']: e for e in history if e['iteration'] > 0}
        different = 0
        for number, row in rows.items():
            entry = entries[number]
            self.assertEqual(entry['parameters'], row['configuration_start'])
            observation = entry['metrics']['extension_observation']
            self.assertEqual(observation['configuration_start'], row['configuration_start'])
            self.assertEqual(observation['configuration_end'], row['configuration_end'])
            different += entry['parameters_after_window'] != entry['parameters']
        self.assertGreater(different, 0, 'The test must exercise changed proposals, not only no-ops')
        for payload in prompts:
            observation = payload['observation']
            if observation.get('window', 0) > 0:
                self.assertEqual(observation['configuration_start'], rows[observation['window']]['configuration_start'])
            for entry in payload['recent_measurements']:
                if entry['iteration'] > 0:
                    self.assertEqual(entry['parameters'], rows[entry['iteration']]['configuration_start'])
        final = next(p for p in prompts if p['final_freeze'])
        self.assertEqual(final['recent_measurements'][-1]['iteration'], 30)
        self.assertEqual(final['recent_measurements'][-1]['parameters'], rows[30]['configuration_start'])
        self.assertEqual(final['controls'], entries[30]['parameters_after_window'])
        self.assertEqual(len({json.dumps(rows[n]['configuration_start'], sort_keys=True) for n in range(31, 51)}), 1)

    def test_mid_window_control_change_is_rejected(self):
        controller = ScopedController.__new__(ScopedController)
        controller.config = SimpleNamespace(window_duration=5)
        controller.param_manager = MagicMock()
        controller.param_manager.snapshot.side_effect = [
            {'application_updates': {}, 'host_updates': {'test_knob': '0'}},
            {'application_updates': {}, 'host_updates': {'test_knob': '1'}}]
        controller.benchmark = MagicMock()
        controller.benchmark.execute_window.return_value = BenchmarkMetrics(extra_metrics={'extension_observation': {}})
        with self.assertRaisesRegex(RuntimeError, 'Controls changed'):
            controller._execute_window_simple(1)

    def test_negative_control_reproduces_old_misattribution(self):
        run_data, history, _ = self.exercise(legacy=True)
        rows = {w['window']: w for w in run_data['windows'] if w['phase'] == 'tuning'}
        wrong = [e['iteration'] for e in history if e['iteration'] in rows and e['parameters'] != rows[e['iteration']]['configuration_start']]
        self.assertGreater(len(wrong), 0, 'Regression must fail against the old record-after-write behavior')
