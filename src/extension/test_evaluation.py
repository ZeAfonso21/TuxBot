"""Plot-only validation: synthetic fixtures/existing files, no runner/workload/API imports."""
import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .evaluation import (control_series, evaluate_pair, improvement, load_pairs, load_run,
                         nondominated, repetition_summary)
from .evaluation_fixture import fixture_runs
from .report import export


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.a, self.c = fixture_runs()

    def save(self, a=None, c=None, suffix=''):
        paths = [self.root / ('A' + suffix + '.json'), self.root / ('C' + suffix + '.json')]
        for path, data in zip(paths, (a or self.a, c or self.c)):
            path.write_text(json.dumps(data))
        return paths

    def pair(self, a=None, c=None, **kwargs):
        left, right = self.save(a, c)
        return evaluate_pair(load_run(left), load_run(right), **kwargs)

    def curve(self, pair, number):
        return next(r for r in pair['curves'] if r['window'] == number)

    def test_formulas_positive_negative_and_not_speedup(self):
        self.assertAlmostEqual(improvement(4, 3.2, 'minimize'), 20)
        self.assertAlmostEqual(improvement(100, 120, 'maximize'), 20)
        self.assertAlmostEqual(improvement(4, 5, 'minimize'), -25)
        self.assertAlmostEqual(improvement(100, 80, 'maximize'), -20)
        self.assertEqual(improvement(4, 4, 'minimize'), 0)

    def test_zero_current_and_missing_are_not_invalid_baselines(self):
        self.assertEqual(improvement(100, 0, 'maximize'), -100)
        self.assertEqual(improvement(4, 0, 'minimize'), 100)
        self.assertIsNone(improvement(4, None, 'minimize'))
        for bad in (0, -1, None, True, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                improvement(bad, 1, 'minimize')
        for bad in (-1, True, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                improvement(1, bad, 'maximize')

    def test_A_needs_no_cgroup_data_and_uses_steady_reference(self):
        pair = self.pair()
        self.assertFalse(pair['a']['dedicated_cgroups'])
        self.assertNotIn('initial_configuration', self.a)
        self.assertEqual(pair['reference'], {'cpu_latency': 4, 'memory_bandwidth': 100})
        self.assertEqual(pair['a_stable_windows'], [3, 4, 5])
        # Initial baseline/bound is 8/50, so this also rules out own-baseline/bound normalization.
        self.assertEqual(self.curve(pair, 1)['improvements'], [-25, 10])
        self.assertEqual(self.curve(pair, -1)['improvements'], [-100, -50])

    def test_null_history_placeholders_are_missing_not_cgroup_evidence(self):
        a, c = copy.deepcopy(self.a), copy.deepcopy(self.c)
        a['initial_configuration'] = {'application_updates': None}
        for window in a['windows']:
            for obs in window['applications'].values():
                obs['cgroup_window'] = None
        c['windows'][4]['configuration_start'] = {'application_updates': None, 'host_updates': None}
        c['windows'][4]['configuration_end'] = copy.deepcopy(c['windows'][4]['configuration_start'])
        c['windows'][4]['observed_host_start'] = None
        pair = self.pair(a, c)
        self.assertFalse(pair['a']['dedicated_cgroups'])
        series = next(s for s in pair['controls'] if s['parameter'] == 'latency_ns')
        self.assertIsNone(series['points'][1]['value'])

    def test_C_is_not_paired_with_unrelated_A_window_indices(self):
        a = copy.deepcopy(self.a)
        for w in a['windows']:
            if w['phase'] == 'tuning':
                w['applications']['cpu_latency']['current'] = 100
        pair = self.pair(a)
        self.assertEqual(self.curve(pair, 1)['improvements'][0], -25)

    def test_stable_summary_is_ratio_of_raw_medians_not_mean_percentages(self):
        pair = self.pair()
        row = pair['summary'][0]
        self.assertEqual(row['coordinated'], 3.2)  # median of 5, 3.2, 3
        self.assertAlmostEqual(row['improvement_pct'], 20)
        average = sum(r['improvements'][0] for r in pair['curves'] if r['phase'] == 'stable') / 3
        self.assertNotAlmostEqual(row['improvement_pct'], average)

    def test_missing_one_metric_never_creates_mismatched_pareto_point(self):
        c = copy.deepcopy(self.c)
        del c['windows'][4]['applications']['memory_bandwidth']
        pair = self.pair(c=c)
        self.assertIsNotNone(self.curve(pair, 2)['improvements'][0])
        self.assertIsNone(self.curve(pair, 2)['improvements'][1])
        self.assertNotIn(2, [p['window'] for p in pair['pareto']])
        curves = {r['window']: r for r in pair['curves']}
        for point in pair['pareto']:
            self.assertEqual(point['improvements'], curves[point['window']]['improvements'])
            self.assertEqual((point['start'], point['end']), (curves[point['window']]['start'], curves[point['window']]['end']))

    def test_incomplete_stable_window_excluded_for_both_metrics(self):
        c = copy.deepcopy(self.c)
        del c['windows'][5]['applications']['memory_bandwidth']
        pair = self.pair(c=c)
        self.assertEqual(pair['c_stable_windows'], [4, 5])
        self.assertAlmostEqual(pair['summary'][0]['coordinated'], 3.1)
        self.assertIn('Incomplete joint stable', ' '.join(pair['notes']))

    def test_cpu_memory_order_uses_metric_identity_not_input_array_order(self):
        a, c = copy.deepcopy(self.a), copy.deepcopy(self.c)
        a['applications'].reverse()
        c['applications'].reverse()
        pair = self.pair(a, c)
        self.assertEqual(pair['apps'], ['cpu_latency', 'memory_bandwidth'])
        self.assertEqual(self.curve(pair, 1)['improvements'], [-25, 10])

    def test_mismatched_cpu_memory_endpoints_rejected(self):
        c = copy.deepcopy(self.c)
        c['windows'][4]['applications']['memory_bandwidth']['raw']['window_end'] = 999
        with self.assertRaisesRegex(ValueError, 'endpoints'):
            self.pair(c=c)

    def test_no_stable_phase_is_not_invented_from_window_number(self):
        a = copy.deepcopy(self.a)
        for row in a['windows']:
            if row['phase'] == 'stable':
                row['phase'] = 'tuning'
        pair = self.pair(a=a)
        self.assertEqual(pair['reference'], {})
        self.assertTrue(all(s['improvement_pct'] is None for s in pair['summary']))
        self.assertFalse(pair['pareto'])

    def test_stable_phase_comes_from_recorded_phase_not_budget_31(self):
        a, c = copy.deepcopy(self.a), copy.deepcopy(self.c)
        for run in (a, c):
            run['config']['tuning_windows'], run['config']['stable_windows'] = 30, 20
        pair = self.pair(a, c)
        self.assertEqual(pair['a_stable_windows'], [3, 4, 5])
        self.assertEqual([r['window'] for r in pair['curves'] if r['phase'] == 'stable'], [3, 4, 5])
        self.assertIn('3 recorded, 20 expected', ' '.join(pair['notes']))

    def test_tuned_failed_or_different_setup_reference_rejected(self):
        for field, value in (('mode', 'coordinated'), ('completed', False)):
            a = copy.deepcopy(self.a)
            a[field] = value
            with self.assertRaises(ValueError):
                self.pair(a)
        c = copy.deepcopy(self.c)
        c['config']['workload_conditions']['cpu_latency']['threads'] = 99
        with self.assertRaisesRegex(ValueError, 'conditions'):
            self.pair(c=c)
        c = copy.deepcopy(self.c)
        c['config']['window_seconds'] = 10
        with self.assertRaisesRegex(ValueError, 'window_seconds'):
            self.pair(c=c)
        c = copy.deepcopy(self.c)
        c['provenance']['concurrent_workloads'] = False
        with self.assertRaisesRegex(ValueError, 'concurrent'):
            self.pair(c=c)

    def test_A_label_does_not_override_actual_tuning_evidence(self):
        a = copy.deepcopy(self.a)
        a['decisions'] = {'unexpected_tuner': [{'proposal': {'host_updates': {'latency_ns': 1}}}]}
        with self.assertRaisesRegex(ValueError, 'tuner/actuation'):
            self.pair(a=a)
        a = copy.deepcopy(self.a)
        a['initial_host_observations'] = {'latency_ns': '24000000'}
        a['windows'][3]['observed_host_start'] = {'latency_ns': '1'}
        with self.assertRaisesRegex(ValueError, 'host controls changed'):
            self.pair(a=a)

    def test_actual_legacy_A_cgroup_evidence_is_not_silently_relabelled(self):
        a = copy.deepcopy(self.a)
        a['provenance']['dedicated_workload_cgroups'] = True
        a['initial_configuration'] = {'application_updates': {'cpu_latency': {'cpu.weight': '100'}}}
        with self.assertRaisesRegex(ValueError, 'no-cgroup'):
            self.pair(a)
        self.assertTrue(self.pair(a, allow_legacy_a=True)['historical'])
        a['provenance']['dedicated_workload_cgroups'] = False
        with self.assertRaisesRegex(ValueError, 'Contradictory'):
            self.pair(a, allow_legacy_a=True)

    def test_unknown_A_provenance_and_mixed_synthetic_data_rejected(self):
        a = copy.deepcopy(self.a)
        del a['provenance']
        with self.assertRaisesRegex(ValueError, 'provenance'):
            self.pair(a)
        a = copy.deepcopy(self.a)
        a['data_kind'] = 'measured'
        with self.assertRaisesRegex(ValueError, 'Synthetic'):
            self.pair(a)

    def test_zero_reference_and_duplicate_windows_rejected(self):
        a = copy.deepcopy(self.a)
        for w in a['windows']:
            if w['phase'] == 'stable':
                w['applications']['cpu_latency']['current'] = 0
        with self.assertRaisesRegex(ValueError, 'strictly positive'):
            self.pair(a)
        c = copy.deepcopy(self.c)
        c['windows'][-1]['window'] = c['windows'][-2]['window']
        with self.assertRaisesRegex(ValueError, 'unique'):
            self.pair(c=c)

    def test_controls_are_readbacks_and_include_discovered_parameters(self):
        c = copy.deepcopy(self.c)
        c['decisions'] = {'coordinated': [{'proposal': {'host_updates': {'PROPOSED_ONLY': 999999}}}]}
        pair = self.pair(c=c)
        names = {s['parameter'] for s in pair['controls']}
        self.assertIn('custom_knob', names)
        self.assertIn('memory.high', names)
        self.assertNotIn('PROPOSED_ONLY', names)
        self.assertNotIn('memory.current', names)
        weights = [s for s in pair['controls'] if s['parameter'] == 'cpu.weight']
        self.assertEqual({s['application'] for s in weights}, {'cpu_latency', 'memory_bandwidth'})
        self.assertEqual([s for s in weights if not s['changed']][0]['application'], 'memory_bandwidth')
        self.assertTrue(any(s['points'][0]['value'] == 'max' for s in pair['controls'] if s['parameter'] == 'memory.high'))

    def test_mixed_window_and_missing_readbacks_not_forward_filled(self):
        c = copy.deepcopy(self.c)
        c['windows'][4]['configuration_end']['host_updates']['latency_ns'] = '1'
        pair = self.pair(c=c)
        series = next(s for s in pair['controls'] if s['parameter'] == 'latency_ns')
        self.assertIsNone(series['points'][1]['value'])
        c = copy.deepcopy(self.c)
        for w in c['windows']:
            for key in ('configuration_start', 'configuration_end', 'observed_host_start'):
                del w[key]
        pair = self.pair(c=c)
        self.assertFalse(pair['controls'])
        self.assertIn('proposed settings are not substituted', ' '.join(pair['notes']))

    def test_pareto_frontier_includes_A_origin_as_competitor(self):
        points = [dict(improvements=v) for v in ([-1, -1], [1, 2], [2, 1], [1, 1])]
        self.assertEqual(nondominated(points), [1, 2])

    def test_explicit_independent_pairs_not_windows_are_statistical_units(self):
        first = self.save(suffix='1')
        a, c = copy.deepcopy(self.a), copy.deepcopy(self.c)
        for data in (a, c):
            for window in data['windows']:
                window['start'] += 100
                window['end'] += 100
                for obs in window['applications'].values():
                    obs['raw']['window_start'] += 100
                    obs['raw']['window_end'] += 100
        second = self.save(a, c, suffix='2')
        manifest = self.root / 'pairs.json'
        definitions = [dict(id=str(i), a=str(paths[0]), c=str(paths[1]), independent_repetition=True) for i, paths in enumerate((first, second))]
        manifest.write_text(json.dumps({'pairs': definitions}))
        pairs = load_pairs(manifest=manifest)
        summaries = repetition_summary(pairs)
        self.assertTrue(all(s['n_pairs'] == 2 for s in summaries))
        self.assertTrue(all('not a confidence' in s['variability'] for s in summaries))
        definitions[1]['a'] = definitions[0]['a']
        manifest.write_text(json.dumps({'pairs': definitions}))
        with self.assertRaisesRegex(ValueError, 'not independent'):
            load_pairs(manifest=manifest)

    def test_missing_whole_window_and_nonfinite_current_are_not_zero(self):
        c = copy.deepcopy(self.c)
        del c['windows'][4]
        c['windows'][4]['applications']['cpu_latency']['current'] = float('nan')
        pair = self.pair(c=c)
        self.assertIn('Missing measurement window IDs: [2]', ' '.join(pair['notes']))
        self.assertIsNone(self.curve(pair, 3)['current'][0])

    def test_report_outputs_four_main_figures_and_no_retired_defaults(self):
        files = self.save()
        before = [p.read_bytes() for p in files]
        out = self.root / 'report'
        out.mkdir()
        (out / 'improvement_per_window.png').write_bytes(b'old output, not a real image')
        metadata = export(files, out, plots=True)
        self.assertEqual(metadata['data_kind'], 'synthetic')
        self.assertEqual(set(metadata['generated_figures']), {'relative_improvement', 'stable_performance', 'pareto_tradeoffs', 'applied_parameters'})
        self.assertFalse((out / 'improvement_per_window.png').exists())
        self.assertTrue((out / 'retired' / 'improvement_per_window.png').is_file())
        self.assertFalse((out / 'resource_telemetry.png').exists())
        for figure in metadata['generated_figures']:
            for suffix in ('png', 'pdf'):
                self.assertTrue((out / (figure + '.' + suffix)).is_file())
        with (out / 'relative_improvement.csv').open() as stream:
            curves = list(csv.DictReader(stream))
        with (out / 'pareto_points.csv').open() as stream:
            points = list(csv.DictReader(stream))
        by_window = {(r['window'], r['application']): r['improvement_pct'] for r in curves}
        for p in points:
            self.assertEqual(p['x_improvement_pct'], by_window[p['window'], p['x_application']])
            self.assertEqual(p['y_improvement_pct'], by_window[p['window'], p['y_application']])
        self.assertEqual(before, [p.read_bytes() for p in files])

    def test_no_C_measurements_skips_figures_instead_of_inventing_zero(self):
        c = copy.deepcopy(self.c)
        c['windows'] = []
        c['completed'] = False
        metadata = export(self.save(c=c), self.root / 'empty-report', plots=True)
        self.assertEqual(metadata['generated_figures'], [])
        self.assertEqual(len(metadata['skipped_figures']), 4)
        self.assertFalse(metadata['all_runs_completed'])

    def test_existing_pilot_is_flagged_and_uses_A_stable_not_initial_reference(self):
        manifest = Path(__file__).resolve().parent / 'examples' / 'evaluation-pilot.json'
        raw = Path(__file__).resolve().parents[2] / 'results' / 'pilot-01' / 'A-default-02' / 'results.json'
        if not raw.exists():
            self.skipTest('Optional historical artifacts not present in this checkout')
        with self.assertRaisesRegex(ValueError, 'no-cgroup'):
            load_pairs(manifest=manifest)
        pair = load_pairs(manifest=manifest, allow_legacy_a=True)[0]
        self.assertTrue(pair['historical'])
        self.assertEqual(pair['a_stable_windows'], [9, 10, 11])
        self.assertAlmostEqual(pair['reference']['memory_bandwidth'], 21577.16285714286)
        self.assertAlmostEqual(pair['summary'][0]['improvement_pct'], 13.624678663239076)
        self.assertAlmostEqual(pair['summary'][1]['improvement_pct'], .8477746379207396)

    def test_future_profiles_are_30_20_and_pairs_are_not_preclassified(self):
        examples = Path(__file__).resolve().parent / 'examples'
        for name in ('default', 'independent', 'coordinated', 'pilot-A', 'pilot-C'):
            data = json.loads((examples / (name + '.json')).read_text())
            self.assertEqual((data['tuning_windows'], data['stable_windows']), (30, 20))
            self.assertEqual(data['window_seconds'], 5)
            if data['mode'] == 'coordinated':
                self.assertEqual(data['reference_policy'], 'stable_mean')
                self.assertTrue(data['reference_run'])
        plan = json.loads((examples / 'workload-pairs.json').read_text())
        self.assertTrue(all(p['relationship'] == 'unmeasured' for p in plan['pairs']))
        for name in ('xapian', 'sphinx', 'sysbench-cpu-throughput'):
            self.assertIsInstance(json.loads((examples / (name + '.json')).read_text()), dict)

    def test_optional_telemetry_never_plots_A_cgroups_or_C_parent_totals(self):
        from .plots import telemetry_figure
        a, c = copy.deepcopy(self.a), copy.deepcopy(self.c)
        a['provenance']['dedicated_workload_cgroups'] = True
        a['config']['cgroup_root'] = '/sys/fs/cgroup/SYNTHETIC-A-NOT-CREATED'
        a['initial_configuration'] = copy.deepcopy(c['initial_configuration'])
        for w in a['windows']:
            w['configuration_start'] = copy.deepcopy(a['initial_configuration'])
            for app in a['applications']:
                w['applications'][app['id']].update(
                    cgroup_window={'cpu_usage_cores': 999, 'memory_current_bytes': 999999},
                    resource_scope={'kind': 'cgroup', 'path': a['config']['cgroup_root'] + '/' + app['id']})
        for w in c['windows']:
            w['applications']['cpu_latency']['resource_scope']['path'] = c['config']['cgroup_root']
        pair = self.pair(a=a, c=c, allow_legacy_a=True)
        names = []
        def capture(fig, *args):
            import matplotlib.pyplot as plt
            names.extend(line.get_label() for ax in fig.axes for line in ax.lines)
            plt.close(fig)
        with patch('extension.plots.finish', side_effect=capture):
            self.assertTrue(telemetry_figure([pair], self.root))
        self.assertFalse(any('Configuration A' in n and 'cgroup' in n for n in names))
        self.assertFalse(any('cpu_latency child cgroup' in n for n in names))
        self.assertTrue(any('memory_bandwidth child cgroup' in n for n in names))


if __name__ == '__main__':
    unittest.main()
