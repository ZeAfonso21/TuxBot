"""Exercise all three complete runner/export paths with fake workloads/interfaces/providers."""
from contextlib import ExitStack
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from .controls import Control
from .controller import ScopedTuner
from .report import export
from .runner import run


class FakeGroups:
    def __init__(self, root, ids):
        self.root = Path(root)
        self.paths = {app: self.root / app for app in ids}
        self.created = []
        self.original_subtree = []

    def create(self):
        for path in self.paths.values():
            path.mkdir(parents=True)
            (path / 'cpu.weight').write_text('100\n')
            (path / 'cgroup.procs').write_text('')
            self.created.append(path)

    def await_empty(self):
        return []

    def cleanup(self):
        return []


class FakeWindows:
    def __init__(self, config, apps, groups, output, tolerance):
        self.apps, self.tolerance = apps, tolerance
        self.rows = []
        self.phase = 'baseline'

    def collect(self, number, duration):
        observations = {}
        for app in self.apps:
            value = 4 if app.id == 'A' else 100
            observations[app.id] = app.observation(value, self.tolerance) if app.baseline else dict(metric=app.metric, objective=app.objective, current=value)
        row = dict(window=number, phase=self.phase, start=len(self.rows), end=len(self.rows) + 1,
                   applications=observations, shared={'test_shared_counter': 1})
        self.rows.append(row)
        return row


class RunnerTests(unittest.TestCase):
    def test_plot_modes_are_distinguishable(self):
        from .plots import COLORS, STYLES, MARKERS
        for mapping in (COLORS, STYLES, MARKERS):
            self.assertEqual(set(mapping), {'default', 'independent', 'coordinated'})
            self.assertEqual(len(set(mapping.values())), 3)

    def test_all_modes_restore_export_and_plot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            host = root / 'host-control'
            host.write_text('0\n')
            result_files = []

            def host_controls(approved):
                return {'napi_busy_poll': Control(host, 0, 1000)}, {'test_only': True}

            def cgroup_controls(path, policy):
                return {'cpu.weight': Control(path / 'cpu.weight', 1, 10000)}

            def transport(tuner, contents, *args, **kwargs):
                manager = tuner.config._extension_runtime.manager
                proposal = dict(application_updates={a: {'cpu.weight': 200} for a in manager.applications},
                                host_updates={'napi_busy_poll': 1} if manager.host else {}, reasoning='mock runner test')
                return json.dumps(proposal), proposal, .001, {}, None, {'input_tokens': 10}

            process = MagicMock()
            process.poll.return_value = None
            process.wait.return_value = 0
            process.pid = 999999999  # killpg is mocked, never passed to the kernel
            with ExitStack() as stack:
                stack.enter_context(patch('extension.runner.Cgroups', FakeGroups))
                stack.enter_context(patch('extension.runner.cgroup_controls', cgroup_controls))
                stack.enter_context(patch('extension.host.resolve_host', host_controls))
                stack.enter_context(patch('extension.telemetry.Windows', FakeWindows))
                stack.enter_context(patch('extension.runner.subprocess.Popen', return_value=process))
                stack.enter_context(patch('extension.runner.os.killpg'))
                stack.enter_context(patch('extension.runner.baseline_membership', return_value=dict(inherited_cgroup='0::/\n', workload_cgroup_membership={'A': '0::/\n', 'B': '0::/\n'})))
                stack.enter_context(patch('optimizer.tuners.llm.genai.Client'))
                stack.enter_context(patch.dict('os.environ', {'GEMINI_API_KEY': 'mock-not-a-real-key'}))
                stack.enter_context(patch.object(ScopedTuner, '_call_llm_with_retries', transport))
                for mode in ('default', 'independent', 'coordinated'):
                    output = root / mode
                    data = dict(mode=mode, defaults_verified=True, data_kind='synthetic',
                                workload_conditions={'A': {'program': 'SYNTHETIC latency'}, 'B': {'program': 'SYNTHETIC throughput'}},
                                cgroup_root=str(root / (mode + '-cgroups')),
                                results_dir=str(output), warmup_seconds=0, window_seconds=1, tuning_windows=2, stable_windows=3,
                                applications=[dict(id='A', metric='latency', objective='minimize', start=['fake'], measure=['fake']),
                                              dict(id='B', metric='throughput', objective='maximize', start=['fake'], measure=['fake'])])
                    if mode == 'default':
                        del data['cgroup_root']
                    run(data)
                    filename = output / 'results.json'
                    result_files.append(filename)
                    result = json.loads(filename.read_text())
                    self.assertTrue(result['completed'])
                    self.assertEqual(result['restoration_errors'], [])
                    self.assertEqual(len(result['windows']), 8)
                    self.assertEqual(result['initial_configuration'], result['effective_after_restore'])
                    self.assertEqual(result['provenance']['dedicated_workload_cgroups'], mode != 'default')
                    if mode == 'default':
                        self.assertFalse((root / 'default-cgroups').exists())
                        self.assertEqual(result['initial_configuration']['application_updates'], {})
                    self.assertEqual([a['baseline'] for a in result['applications']], [4, 100])
                    self.assertEqual(host.read_text().strip(), '0')
                    if mode != 'default':
                        self.assertTrue(all(r['history_file'] for r in result['controllers']))
            metadata = export([result_files[0], result_files[2]], root / 'report', plots=True)
            self.assertEqual(metadata['data_kind'], 'synthetic')
            with (root / 'report' / 'paired_summary.csv').open() as stream:
                summaries = list(csv.DictReader(stream))
            self.assertEqual(len(summaries), 2)
            self.assertTrue(all(r['n_pairs'] == '1' for r in summaries))
            for name in ('relative_improvement', 'stable_performance', 'pareto_tradeoffs'):
                self.assertTrue((root / 'report' / (name + '.png')).is_file())
                self.assertTrue((root / 'report' / (name + '.pdf')).is_file())
            self.assertFalse((root / 'report' / 'applied_parameters.png').exists())  # fake collector recorded no readbacks
            self.assertFalse((root / 'report' / 'resource_telemetry.png').exists())  # opt-in only


if __name__ == '__main__':
    unittest.main()
