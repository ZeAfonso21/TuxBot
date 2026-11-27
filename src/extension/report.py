"""Offline A/C evaluation; no workloads, optimizers, APIs or privileged writes."""
import argparse
import csv
import json
import math
from pathlib import Path
from .evaluation import DISPLAY, load_pairs, repetition_summary

REPORT_VERSION = 2
FIGURES = ('relative_improvement', 'stable_performance', 'applied_parameters', 'pareto_tradeoffs', 'resource_telemetry')
OBSOLETE = ('improvement_per_window', 'improvement_vs_configuration_A', 'cpu_latency', 'memory_bandwidth',
            'host_telemetry', 'application_resources', 'control_trajectory')


def write_csv(path, rows):
    with Path(path).open('w', newline='') as stream:
        if rows:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def retire_figures(output):
    """Archive only known generated figures; never delete raw results or arbitrary files."""
    retired = []
    for name in OBSOLETE + FIGURES:
        for suffix in ('png', 'pdf'):
            source = output / f'{name}.{suffix}'
            if not source.exists():
                continue
            destination = output / 'retired' / source.name
            destination.parent.mkdir(exist_ok=True)
            index = 1
            while destination.exists():
                destination = destination.with_name(f'{source.stem}.{index}.{suffix}')
                index += 1
            source.rename(destination)
            retired.append(str(destination.relative_to(output)))
    return retired


def bounds_rows(pair):
    rows = []
    for side in ('a', 'c'):
        run = pair[side]
        specs = {a['id']: a for a in run['data'].get('applications', [])}
        for window in run['windows']:
            if window['phase'] in ('baseline', 'warmup'):
                continue
            for app, specification in run['apps'].items():
                observation = (window['raw'].get('applications') or {}).get(app) or {}
                if not isinstance(observation, dict):
                    continue
                bound = observation.get('bound')
                origin = specs.get(app, {}).get('bound')
                value = window['values'][app]
                if type(bound) not in (int, float) or not math.isfinite(bound) or value is None:
                    continue
                violation = value > bound if specification['objective'] == 'minimize' else value < bound
                rows.append(dict(pair=pair['id'], configuration=DISPLAY[run['mode']], application=app,
                                 window=window['window'], phase=window['phase'], metric=specification['metric'],
                                 objective=specification['objective'], value=value, bound=bound, violation=violation,
                                 bound_source=('shared A initial mean' if run['data'].get('baseline_reference') or pair['reference_policy'] == 'initial_mean' else 'own run measured initial baseline; NOT the A evaluation reference') if origin == 'default' else 'explicit or recorded run bound'))
    return rows


def export(files, output, plots=False, *, pairs_manifest=None, allow_legacy_a=False, telemetry=False):
    """Historical JSON stays readable; no-cgroup A validation is strict unless explicitly waived."""
    if telemetry and not plots:
        raise ValueError('--telemetry requires plot generation (--plots)')
    pairs = load_pairs(files, pairs_manifest, allow_legacy_a)
    output = Path(output).resolve()
    if any(output == Path(p[side]['source']).parent for p in pairs for side in ('a', 'c')):
        raise ValueError('Report output must be separate from raw run directories')
    output.mkdir(parents=True, exist_ok=True)
    metadata = dict(report_version=REPORT_VERSION,
                    comparison_status='historical_nonconforming_A' if any(p['historical'] for p in pairs) else 'protocol_compatible_recorded_data',
                    data_kind='synthetic' if any(p['synthetic'] for p in pairs) else 'measured',
                    all_runs_completed=all(p[side]['data'].get('completed') is True for p in pairs for side in ('a', 'c')),
                    reference_strategy=pairs[0]['reference_description'],
                    formulas=dict(minimize='100 * (A - C) / A', maximize='100 * (C - A) / A'),
                    aggregation=pairs[0]['stable_aggregation'] + ' of complete joint C stable-window metrics; NOT pooled request p99',
                    repetition_unit='explicitly paired independent runs, never individual windows',
                    no_window_index_pairing=True, pairs=[], generated_figures=[], skipped_figures=[],
                    retired_outputs=retire_figures(output) if plots else [])
    trajectories, summary, pareto, controls, bounds, inference, raw_metrics = [], [], [], [], [], [], []
    for pair in pairs:
        metadata['pairs'].append(dict(id=pair['id'], a_source=pair['a']['source'], c_source=pair['c']['source'],
                                      a_sha256=pair['a']['sha256'], c_sha256=pair['c']['sha256'],
                                      a_dedicated_workload_cgroups=pair['a']['dedicated_cgroups'],
                                      workload_equivalence=pair['conditions'], a_reference=pair['reference'],
                                      reference_policy=pair['reference_policy'], a_selected_reference_windows=pair['reference_windows'],
                                      warmup_seconds={side: pair[side]['data'].get('config', {}).get('warmup_seconds') for side in ('a', 'c')},
                                      window_seconds={side: pair[side]['data'].get('config', {}).get('window_seconds') for side in ('a', 'c')},
                                      a_selected_stable_windows=pair['a_stable_windows'], c_selected_stable_windows=pair['c_stable_windows'],
                                      phase_counts={side: {phase: sum(w['phase'] == phase for w in pair[side]['windows']) for phase in ('warmup', 'baseline', 'tuning', 'stable', 'measurement')} for side in ('a', 'c')},
                                      notes=pair['notes']))
        for row in pair['curves']:
            for index, app in enumerate(pair['apps']):
                trajectories.append(dict(pair=pair['id'], configuration=DISPLAY['coordinated'], window=row['window'],
                                         phase=row['phase'], start=row['start'], end=row['end'], application=app,
                                         metric=pair['specs'][app]['metric'], objective=pair['specs'][app]['objective'],
                                         a_reference=pair['reference'].get(app), current=row['current'][index],
                                         improvement_pct=row['improvements'][index]))
        for row in pair['summary']:
            summary.append(dict(pair=pair['id'], **row, a_stable_windows=len(pair['a_stable_windows']),
                                c_stable_windows=len(pair['c_stable_windows']), a_reference_windows=len(pair['reference_windows']),
                                aggregate=pair['stable_aggregation'] + ' of complete joint C stable-window metrics'))
        for index, point in enumerate(pair['pareto']):
            pareto.append(dict(pair=pair['id'], window=point['window'], phase=point['phase'], start=point['start'], end=point['end'],
                               x_application=pair['apps'][0], y_application=pair['apps'][1],
                               x_improvement_pct=point['improvements'][0], y_improvement_pct=point['improvements'][1],
                               observed_nondominated=index in pair['frontier_indices']))
        for series in pair['controls']:
            for point in series['points']:
                controls.append(dict(pair=pair['id'], configuration=DISPLAY['coordinated'], scope=series['scope'],
                                     application=series['application'], parameter=series['parameter'],
                                     initial=series['initial'], modified=series['changed'], **point, source='actual window-start readback'))
        bounds.extend(bounds_rows(pair))
        for records in pair['c']['data'].get('decisions', {}).values():
            for record in records:
                inference.append(dict(pair=pair['id'], timestamp=record.get('timestamp'), role=record.get('role'),
                                      response_seconds=record.get('response_time'), token_metrics=json.dumps(record.get('token_metrics')),
                                      error=record.get('error'), proposed_updates=json.dumps(record.get('proposal'))))
        for side in ('a', 'c'):
            for window in pair[side]['windows']:
                for app, value in window['values'].items():
                    raw_metrics.append(dict(pair=pair['id'], configuration=DISPLAY[pair[side]['mode']], window=window['window'],
                                            phase=window['phase'], start=window['start'], end=window['end'], application=app,
                                            metric=pair['specs'][app]['metric'], value=value))
    for name, rows in (('relative_improvement', trajectories), ('stable_summary', summary), ('pareto_points', pareto),
                       ('applied_controls', controls), ('performance_bounds', bounds), ('inference', inference),
                       ('raw_metrics', raw_metrics), ('paired_summary', repetition_summary(pairs))):
        write_csv(output / f'{name}.csv', rows)
    if plots:
        from .plots import relative_figure, stable_figure, parameter_figure, pareto_figure, telemetry_figure
        for name, function in zip(FIGURES[:4], (relative_figure, stable_figure, parameter_figure, pareto_figure)):
            if function(pairs, output):
                metadata['generated_figures'].append(name)
            else:
                metadata['skipped_figures'].append(name + ': required complete stable references or actual control history unavailable; see pair notes')
        if telemetry:
            if telemetry_figure(pairs, output):
                metadata['generated_figures'].append('resource_telemetry')
            else:
                metadata['skipped_figures'].append('resource_telemetry: insufficient reliably scoped observations')
    metadata['telemetry_policy'] = ('Optional; host counters are shared, A per-app cgroup data are never plotted; '
                                    'A process data require explicit process-tree scope, C data require child-cgroup mapping. '
                                    'Unavailable A process metrics are not synthesized. IPC may be rounded by the original perf parser.')
    (output / 'evaluation.json').write_text(json.dumps(metadata, indent=2, allow_nan=False) + '\n')
    lines = ['# Configuration A vs C evaluation', '', f"Status: **{metadata['comparison_status']}**; data: **{metadata['data_kind']}**.",
             '', 'Reference: ' + metadata['reference_strategy'] + ', fixed for every C window of its run pair.',
             'Latency uses 100 × (A − C) / A; throughput uses 100 × (C − A) / A. These are ordinary reductions/increases, not speedup-factor percentages.',
             'Reference selection follows the declared policy; no A/C window-index pairing occurs.',
             'C stable aggregation: ' + metadata['aggregation'] + '. Percentages are calculated after raw aggregation.',
             'Each summary point is one A/C run pair. With multiple pairs the displayed range is descriptive run-pair variability, not a confidence interval.',
             '', '## Sources and quality notes']
    for pair in metadata['pairs']:
        lines.extend(['', f"### {pair['id']}", f"A: `{pair['a_source']}`", f"C: `{pair['c_source']}`",
                      f"A reference: `{pair['a_reference']}`; selected A reference windows: {pair['a_selected_reference_windows']}; C windows: {pair['c_selected_stable_windows']}."])
        lines.append('Workload equivalence: ' + pair['workload_equivalence']['method'] + '.')
        if 'evidence' in pair['workload_equivalence']:
            lines.append(pair['workload_equivalence']['evidence'])
        lines.append(f"Recorded warmup seconds: {pair['warmup_seconds']}; measurement seconds per window: {pair['window_seconds']}.")
        lines.extend('- ' + note for note in pair['notes'])
    lines.extend(['', '## Figures', *['- ' + name for name in metadata['generated_figures']],
                  *['- SKIPPED: ' + note for note in metadata['skipped_figures']], '', 'Bounds are separate in performance_bounds.csv; they never set the A normalization reference.',
                  metadata['telemetry_policy'], '', 'Historical own-baseline/factor/bound-marker/resource plots are not generated by this report. Known pre-existing figure outputs are archived under retired/ when regenerating.'])
    (output / 'evaluation.md').write_text('\n'.join(lines) + '\n')
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results', nargs='*')
    parser.add_argument('--pairs', help='JSON manifest with explicit A/C run pairs and optional audited workload equivalence')
    parser.add_argument('--output', required=True)
    parser.add_argument('--plots', action='store_true')
    parser.add_argument('--telemetry', action='store_true', help='Opt-in scoped diagnostic figure')
    parser.add_argument('--allow-legacy-a', action='store_true', help='HISTORICAL DIAGNOSTICS ONLY: allow an A run with dedicated default cgroups/unknown provenance')
    args = parser.parse_args()
    if args.pairs and args.results:
        parser.error('Use either result paths or --pairs, not both')
    try:
        export(args.results, args.output, args.plots, pairs_manifest=args.pairs,
               allow_legacy_a=args.allow_legacy_a, telemetry=args.telemetry)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
