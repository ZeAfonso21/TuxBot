"""Remote-safe controller integration: temporary files, mocked SDK, no host writes/API."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from optimizer.config import SimpleConfig
from .controls import Actuator, Control
from .controller import ScopedController, ScopedTuner
from .model import Application
from .telemetry import View, WindowBroker


class Collector:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def collect(self, number, duration):
        self.calls += 1
        if self.fail:
            raise ValueError('Missing application measurement')
        return dict(window=number, phase=self.phase, start=number, end=number + 1,
                    applications={
                        'A': dict(metric='private_latency_A', current=4, improvement=1, significant_regression=False),
                        'B': dict(metric='private_throughput_B', current=100, improvement=1, significant_regression=False)},
                    shared={'private_host_counter': 123})


class ControllerTests(unittest.TestCase):
    def exercise(self, coordinated, fail=False, storage_fail=False):
        prompts = []
        collector = Collector(fail)
        broker = WindowBroker(collector, 1 if coordinated else 2, 10)
        broker.tuning_windows = 2
        apps = [Application('A', 'private_latency_A', 'minimize', ['unused'], ['unused']),
                Application('B', 'private_throughput_B', 'maximize', ['unused'], ['unused'])]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            controls = {}
            for app in apps:
                file = root / app.id
                file.write_text('100\n')
                controls[app.id] = {'cpu.weight': Control(file, 1, 10000)}
            hostfile = root / 'host'
            hostfile.write_text('0\n')
            controllers = []

            def transport(tuner, contents, *args, **kwargs):
                self.assertNotIn('additionalProperties', json.dumps(tuner._build_response_schema()))
                with self.assertRaises(ValueError):
                    tuner._parse_structured_response({'commands': ['not permitted']})
                prompts.append((tuple(tuner.config._extension_runtime.manager.applications), contents))
                proposal = dict(application_updates={app: {'cpu.weight': 200} for app in tuner.config._extension_runtime.manager.applications},
                                host_updates={'napi_busy_poll': 1} if coordinated else {}, reasoning='mock test')
                return json.dumps(proposal), proposal, .001, {}, None, {'input_tokens': 10}

            with patch('optimizer.tuners.llm.genai.Client'), patch.dict('os.environ', {'GEMINI_API_KEY': 'mock-not-a-real-key'}), patch.object(ScopedTuner, '_call_llm_with_retries', transport):
                for selection in ([apps] if coordinated else [[a] for a in apps]):
                    manager = Actuator({a.id: controls[a.id] for a in selection},
                                       {'napi_busy_poll': Control(hostfile, 0, 1000)} if coordinated else {})
                    config = SimpleConfig()
                    config.parameter_ranges, config.fixed_parameters = {}, {}
                    config.optimization_metric, config.optimization_goal = 'extension_reward', 'maximize'
                    config.max_iterations, config.post_tuning_windows = 2, 1
                    config.window_duration = 1
                    config.tuning_mode = 'outside-of-window'
                    config.dual_loop_force_final_actor_before_stable = True
                    config.results_dir = str(root / 'histories' / selection[0].id)
                    config.llm_api_log_enabled = False
                    config._extension_runtime = SimpleNamespace(
                        manager=manager, tuner_class=ScopedTuner, coordinated=coordinated,
                        baseline={'applications': {a.id: {'metric': a.metric, 'baseline': 4 if a.id == 'A' else 100} for a in selection}},
                        decisions=[], bad_windows=0, regression_windows=3)
                    controllers.append(ScopedController(config, View(broker, selection, coordinated)))
                storage = patch.object(ScopedController, '_save_history', side_effect=OSError('simulated storage failure')) if storage_fail else nullcontext()
                with storage, ThreadPoolExecutor(max_workers=len(controllers)) as pool:
                    results = list(pool.map(lambda c: c.run(), controllers))
            self.assertTrue(all(r['terminated_reason'] == ('error' if fail or storage_fail else 'completed') for r in results), results)
            if storage_fail:
                self.assertTrue(all(r.get('history_error') for r in results))
                return
            self.assertTrue(all(r['history_file'] and Path(r['history_file']).is_file() for r in results))
            if not fail:
                self.assertEqual(collector.calls, 3)
                for controller in controllers:
                    self.assertEqual(len(controller.history), 4)
                    self.assertTrue(controller.history[-1]['post_tuning_phase'])
                    self.assertTrue(controller.final_actor_timing)
                    self.assertTrue(controller.config._extension_runtime.decisions)
                self.assertEqual(hostfile.read_text().strip(), '1' if coordinated else '0')
                for ids, contents in prompts:
                    text = '\n'.join(contents)
                    if not coordinated:
                        forbidden = 'private_throughput_B' if ids == ('A',) else 'private_latency_A'
                        self.assertNotIn(forbidden, text)
                        self.assertNotIn('private_host_counter', text)
                        self.assertNotIn('napi_busy_poll', text)
                for controller in controllers:
                    self.assertEqual(controller.param_manager.restore(), [])
                self.assertEqual([controls[a.id]['cpu.weight'].read() for a in apps], ['100', '100'])
                self.assertEqual(hostfile.read_text().strip(), '0')

    def test_coordinated_dual_loop(self):
        self.exercise(True)

    def test_independent_private_dual_loops(self):
        self.exercise(False)

    def test_measurement_failure_aborts_both(self):
        self.exercise(False, fail=True)

    def test_storage_failure_cannot_claim_completion(self):
        self.exercise(True, storage_fail=True)


if __name__ == '__main__':
    unittest.main()
