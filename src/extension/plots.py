"""A/C presentation plots from the shared, read-only evaluation model."""
import math
from pathlib import Path
from statistics import median
import matplotlib.pyplot as plt
from .evaluation import DISPLAY

COLORS = {'default': '#0072B2', 'coordinated': '#D55E00', 'independent': '#009E73'}
STYLES = {'default': '--', 'coordinated': '-', 'independent': '-.'}
MARKERS = {'default': 'o', 'coordinated': 's', 'independent': 'D'}
LABELS = {'latency_p99_ms': 'Sysbench CPU p99 latency (ms)',
          'throughput_mib_s': 'Sysbench Memory throughput (MiB/s)'}


def label(pair, app):
    return LABELS.get(pair['specs'][app]['metric'], f"{app}: {pair['specs'][app]['metric']}")


def finish(fig, output, name, pairs):
    warnings = []
    if any(p['synthetic'] for p in pairs):
        warnings.append('SYNTHETIC FIXTURE — not experimental evidence')
    if any(p['historical'] for p in pairs):
        warnings.append('HISTORICAL DIAGNOSTIC ONLY — A had workload cgroups; not the requested no-cgroup baseline')
    if any(p['c']['data'].get('completed') is not True for p in pairs):
        warnings.append('INCOMPLETE C RUN — available-window diagnostics only')
    if warnings:
        fig.text(.5, .005, '\n'.join(warnings), ha='center', fontsize=8, color='#a32626')
    fig.tight_layout(rect=(0, .10 if warnings else .07, 1, .94))
    for suffix in ('png', 'pdf'):
        fig.savefig(Path(output) / f'{name}.{suffix}', dpi=200, bbox_inches='tight')
    plt.close(fig)


def stable_regions(ax, rows):
    """Only shade stable runs explicitly recorded in the data; never assume window 31."""
    stable = sorted(r['window'] for r in rows if r['phase'] == 'stable')
    if not stable:
        return
    start = last = stable[0]
    for number in stable[1:] + [None]:
        if number is not None and number == last + 1:
            last = number
            continue
        ax.axvspan(start - .45, last + .45, color='#6c7a89', alpha=.10)
        ax.axvline(start - .45, color='#6c7a89', linestyle=':', linewidth=.8)
        if number is not None:
            start = last = number


def zero_scale(ax, values):
    finite = [v for v in values if v is not None and math.isfinite(v)] + [0]
    low, high = min(finite), max(finite)
    padding = max((high - low) * .15, .5)
    ax.set_ylim(low - padding, high + padding)
    ax.axhline(0, color=COLORS['default'], linestyle='--', linewidth=1,
               label='Configuration A — Untuned (0% reference)')
    ax.grid(axis='y', alpha=.18)


def relative_figure(pairs, output):
    usable = [p for p in pairs if p['reference'] and any(any(v is not None for v in r['improvements']) for r in p['curves'])]
    if not usable:
        return False
    fig, axes = plt.subplots(2, 1, figsize=(10, 7.5), sharex=True)
    for index, (app, ax) in enumerate(zip(usable[0]['apps'], axes)):
        all_values = []
        for position, pair in enumerate(usable):
            rows = pair['curves']
            initial = [r for r in rows if r['phase'] == 'baseline' and r['improvements'][index] is not None]
            if initial:
                initial_values = [r['improvements'][index] for r in initial]
                all_values.extend(initial_values)
                ax.scatter([r['window'] for r in initial], initial_values, marker='^', s=30,
                           color=COLORS['coordinated'], label='Configuration C — initial samples' if position == 0 else None)
            by_number = {r['window']: r['improvements'][index] for r in rows if r['phase'] != 'baseline'}
            numbers = list(range(min(by_number), max(by_number) + 1)) if by_number else []
            values = [by_number.get(n) for n in numbers]
            all_values.extend(values)
            if not any(v is not None for v in values):
                continue
            name = DISPLAY['coordinated'] + (f' (pair {position + 1})' if len(usable) > 1 else '')
            ax.plot(numbers, [float('nan') if v is None else v for v in values],
                    color=COLORS['coordinated'], marker='s', markersize=4,
                    linestyle=('-', '-.', ':')[position % 3], label=name)
            stable_regions(ax, rows)
        zero_scale(ax, all_values)
        if not any(v is not None for v in all_values):
            ax.text(.5, .5, 'No valid C observations for this metric', ha='center', transform=ax.transAxes)
        ax.set(title=label(usable[0], app), ylabel='Improvement over Configuration A (%)')
        ax.legend(fontsize=8, loc='best')
    axes[-1].set_xlabel('Recorded measurement window ID (triangles = initial C samples; shaded = stable phase)')
    fig.suptitle('Coordinated tuning improvement relative to untuned Configuration A')
    fig.text(.5, .045, 'Reference: A stable-window medians; CPU uses window-level p99 summaries, not pooled request p99.\nNo A/C window-index pairing.', ha='center', fontsize=8)
    finish(fig, output, 'relative_improvement', pairs)
    return True


def stable_figure(pairs, output):
    if not any(s['improvement_pct'] is not None for p in pairs for s in p['summary']):
        return False
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))
    for index, (app, ax) in enumerate(zip(pairs[0]['apps'], axes)):
        points = [p['summary'][index] for p in pairs if p['summary'][index]['improvement_pct'] is not None]
        values = [s['improvement_pct'] for s in points]
        if values:
            center = median(values)
            ax.bar([0], [center], color=COLORS['coordinated'], alpha=.75, width=.45)
            # Variability unit is a paired experiment, NEVER its constituent windows.
            if len(values) > 1:
                ax.errorbar([0], [center], yerr=[[center - min(values)], [max(values) - center]],
                            color='black', capsize=5, fmt='none', label='Observed paired-run range (not CI)')
            offsets = [0] if len(values) == 1 else [-.12 + .24 * i / (len(values) - 1) for i in range(len(values))]
            ax.scatter(offsets, values, color='black', s=22, zorder=3, label='One point per A/C run pair')
            ax.text(.98, .97, f'{center:+.2f}%', transform=ax.transAxes, ha='right', va='top', fontsize=13)
            if len(points) == 1:
                unit = 'ms' if pairs[0]['specs'][app]['metric'] == 'latency_p99_ms' else 'MiB/s' if pairs[0]['specs'][app]['metric'] == 'throughput_mib_s' else 'raw units'
                ax.text(.5, -.20, f"A: {points[0]['reference']:.3f} → C: {points[0]['coordinated']:.3f} {unit}", transform=ax.transAxes, ha='center', fontsize=9)
        zero_scale(ax, values)
        ax.set(title=label(pairs[0], app), ylabel='Improvement over Configuration A (%)',
               xticks=[0], xticklabels=[DISPLAY['coordinated']], xlim=(-.6, .6))
    fig.suptitle('Stable-phase performance improvement: coordinated vs untuned')
    count = len([p for p in pairs if all(s['improvement_pct'] is not None for s in p['summary'])])
    note = 'Descriptive: one run pair; no confidence interval.' if count == 1 else f'{count} explicitly paired repetitions; dots/ranges describe run pairs, not windows; no confidence interval.'
    fig.text(.5, .055, note, ha='center', fontsize=8)
    finish(fig, output, 'stable_performance', pairs)
    return True


def pareto_figure(pairs, output):
    if not any(p['pareto'] for p in pairs):
        return False
    fig, ax = plt.subplots(figsize=(8, 7))
    xs, ys = [0], [0]
    for position, pair in enumerate(pairs):
        points = pair['pareto']
        for phase, marker in (('baseline', '^'), ('tuning', 'o'), ('stable', 's'), ('measurement', 'p')):
            chosen = [p for p in points if p['phase'] == phase]
            if chosen:
                ax.scatter([p['improvements'][0] for p in chosen], [p['improvements'][1] for p in chosen],
                           color=COLORS['coordinated'], marker=marker, s=42,
                           label=f"Configuration C — {'initial samples' if phase == 'baseline' else phase}" if position == 0 else None)
        annotations = {}
        x_tolerance = max([p['improvements'][0] for p in points] + [1]) * .015
        y_tolerance = max([p['improvements'][1] for p in points] + [.1]) * .025
        for i, point in enumerate(points):
            x, y = point['improvements']
            xs.append(x)
            ys.append(y)
            if len(points) <= 15 and len(pairs) == 1:
                nearby = next((xy for xy in annotations if abs(xy[0] - x) <= x_tolerance and abs(xy[1] - y) <= y_tolerance), (x, y))
                annotations.setdefault(nearby, []).append(str(point['window']))
            if i in pair['frontier_indices']:
                ax.scatter([x], [y], facecolors='none', edgecolors='black', s=125, linewidth=1,
                           label='Observed nondominated windows' if position == 0 and i == pair['frontier_indices'][0] else None)
        for coordinate, windows in annotations.items():
            ax.annotate(','.join(windows), coordinate, xytext=(5, 5), textcoords='offset points', fontsize=8)
    ax.scatter([0], [0], marker='*', s=150, color=COLORS['default'], label='Configuration A — Untuned')
    ax.axhline(0, color='gray', linestyle='--', linewidth=.8)
    ax.axvline(0, color='gray', linestyle='--', linewidth=.8)
    xpad, ypad = max((max(xs) - min(xs)) * .2, 1), max((max(ys) - min(ys)) * .2, 1)
    ax.set_xlim(min(xs) - xpad, max(xs) + xpad)
    ax.set_ylim(min(ys) - ypad, max(ys) + ypad)
    ax.axvspan(0, ax.get_xlim()[1], ymin=(0 - ax.get_ylim()[0]) / (ax.get_ylim()[1] - ax.get_ylim()[0]),
               ymax=1, color='#009E73', alpha=.06)
    ax.set(xlabel=label(pairs[0], pairs[0]['apps'][0]) + ' improvement (%)',
           ylabel=label(pairs[0], pairs[0]['apps'][1]) + ' improvement (%)')
    ax.grid(alpha=.15)
    ax.legend(fontsize=8, loc='best')
    fig.suptitle('Joint performance trade-offs relative to Configuration A')
    fig.text(.5, .04, 'Each point uses both metrics from ONE C window. Upper right benefits both; rings are an observed frontier, not a global optimum.', ha='center', fontsize=8)
    finish(fig, output, 'pareto_tradeoffs', pairs)
    return True


def parameter_group(series):
    name = series['parameter']
    scheduler = {'latency_ns', 'min_granularity_ns', 'wakeup_granularity_ns', 'migration_cost_ns'}
    if series['scope'] == 'host' and name in scheduler:
        return ('host', 'Scheduler times (ms)'), 1e6
    if series['scope'] == 'host' and name in ('min_perf_pct', 'max_perf_pct'):
        return ('host', 'Intel P-state controls (%)'), 1
    if series['scope'] == 'host' and name in ('napi_busy_poll', 'busy_poll', 'busy_read'):
        return ('host', 'Network polling budgets (µs)'), 1
    if name == 'cpu.weight':
        return ('application', 'cpu.weight (relative weight)'), 1
    if name == 'cpu.max':
        return ('application', 'cpu.max (quota µs / period µs; max = unlimited)'), 1
    if name in ('memory.high', 'memory.max'):
        return ('application', name + ' (configured bytes or max)'), 1
    return (series['scope'], name + ' (raw units; unit metadata unavailable)'), 1


def parameter_figure(pairs, output):
    groups = {}
    for position, pair in enumerate(pairs):
        for series in pair['controls']:
            group, scale = parameter_group(series)
            groups.setdefault(group, []).append((position, pair, series, scale))
    if not groups:
        return False
    fig, axes = plt.subplots(len(groups), 1, figsize=(11, max(4, len(groups) * 2.6)), squeeze=False)
    for ax, ((scope, unit), members) in zip(axes[:, 0], groups.items()):
        raw_values = [p['value'] for _, _, s, _ in members for p in s['points'] if p['value'] is not None]
        raw_values += [s['initial'] for _, _, s, _ in members if s['initial'] is not None]
        numeric = True
        try:
            numeric = all(math.isfinite(float(v)) for v in raw_values)
        except (ValueError, TypeError):
            numeric = False
        categories = list(dict.fromkeys(str(v) for v in raw_values)) if not numeric else []
        for series_index, (position, pair, series, scale) in enumerate(members):
            def encode(value):
                if value is None:
                    return float('nan')
                return float(value) / scale if numeric else categories.index(str(value))
            points = {p['window']: p['value'] for p in series['points']}
            windows = list(range(min(points), max(points) + 1)) if points else []
            metric = pair['specs'].get(series['application'], {}).get('metric')
            workload_name = 'Sysbench CPU' if metric == 'latency_p99_ms' else 'Sysbench Memory' if metric == 'throughput_mib_s' else series['application']
            name = series['parameter'] if scope == 'host' else workload_name + ' — ' + series['parameter']
            if len(pairs) > 1:
                name += f' (pair {position + 1})'
            initial = series['initial']
            if initial is not None:
                name += f' [initial {float(initial) / scale:g}]' if numeric else f' [initial {initial}]'
            line, = ax.step(windows, [encode(points.get(n)) for n in windows], where='post', label=name, linewidth=1.5,
                            color=COLORS['coordinated'], linestyle=('-', '--', '-.', ':')[series_index % 4])
            if initial is not None:
                ax.axhline(encode(initial), color='gray', linestyle=':', alpha=.4, linewidth=.8)
            ax.plot(windows, [encode(points.get(n)) for n in windows], linestyle='none', marker=('o', 's', '^', 'D')[series_index % 4], markersize=3, color=line.get_color())
        for pair_index in {m[0] for m in members}:
            stable_regions(ax, pairs[pair_index]['curves'])
        if not numeric:
            ax.set_yticks(range(len(categories)), categories)
        ylabel = 'Time (ms)' if 'Scheduler times' in unit else 'P-state (%)' if 'Intel P-state' in unit else 'Relative weight' if 'cpu.weight' in unit else 'Recorded value / state'
        ax.set(title=('Host-wide — ' if scope == 'host' else 'Per-workload cgroups — ') + unit,
               ylabel=ylabel, xlabel='Measurement window')
        ax.grid(axis='y', alpha=.15)
        ax.legend(fontsize=7, ncol=2)
    fig.suptitle('Coordinated tuning: applied cgroup and host-wide parameter evolution')
    fig.text(.5, .035, 'Steps connect actual C window-start readbacks; exact between-window write times are not inferred. Dotted lines = captured initial values.', ha='center', fontsize=8)
    finish(fig, output, 'applied_parameters', pairs)
    return True


def telemetry_figure(pairs, output):
    """Optional scoped diagnostics; never show A workload-cgroup series, even for historical A."""
    panels = {}
    for pair in pairs:
        for side in ('a', 'c'):
            run = pair[side]
            for metric, unit in (('cpu_load_socket0_pct', 'Host socket CPU load (%)'),
                                 ('instructions_per_cycle', 'Host IPC (all measured CPUs)'),
                                 ('power_socket0_watts', 'Host socket package power (W)')):
                points = [(w['window'], w['raw'].get('shared', {}).get(metric)) for w in run['windows'] if w['phase'] not in ('baseline', 'warmup')]
                valid = [(x, y) for x, y in points if type(y) in (int, float) and math.isfinite(y)]
                if valid:
                    panels.setdefault(unit, []).append((DISPLAY[run['mode']], valid, COLORS[run['mode']]))
            for app in run['apps']:
                for metric, unit, scale in (('cpu_usage_cores', 'Cgroup CPU consumption (core-equivalents)', 1),
                                            ('memory_current_bytes', 'Cgroup memory.current (MiB; NOT a configured limit)', 1024 ** 2)):
                    if side != 'c':
                        continue
                    points = []
                    for window in run['windows']:
                        if window['phase'] in ('baseline', 'warmup'):
                            continue
                        raw_app = (window['raw'].get('applications') or {}).get(app) or {}
                        if not isinstance(raw_app, dict):
                            continue
                        # Require the known per-child adapter mapping; explicit parent aggregation is rejected.
                        root = run['data'].get('config', {}).get('cgroup_root')
                        scope = raw_app.get('resource_scope') or {}
                        trusted = (root and app in ((window['raw'].get('configuration_start') or {}).get('application_updates') or {})
                                   and 'cgroup_before' in raw_app and 'cgroup_after' in raw_app)
                        if scope:
                            trusted = bool(root and scope.get('kind') == 'cgroup' and scope.get('path') == str(Path(root) / app))
                        value = (raw_app.get('cgroup_window') or {}).get(metric)
                        if trusted and type(value) in (int, float) and math.isfinite(value) and value >= 0:
                            points.append((window['window'], value / scale))
                    if points:
                        panels.setdefault(unit, []).append((f'Configuration C — {app} child cgroup', points, COLORS['coordinated']))
            # A process-level metrics are optional, explicit process-tree accounting only.
            if side == 'a':
                for app in run['apps']:
                    for metric, unit, scale in (('cpu_usage_cores', 'Process-tree CPU consumption (core-equivalents)', 1),
                                               ('memory_rss_bytes', 'Process-tree RSS (MiB; not cgroup memory.current)', 1024 ** 2)):
                        points = []
                        for window in run['windows']:
                            observation = (window['raw'].get('applications') or {}).get(app) or {}
                            if not isinstance(observation, dict):
                                continue
                            scope = observation.get('resource_scope') or {}
                            value = (observation.get('process_window') or {}).get(metric)
                            if window['phase'] not in ('baseline', 'warmup') and scope.get('kind') == 'process_tree' and type(value) in (int, float) and math.isfinite(value) and value >= 0:
                                points.append((window['window'], value / scale))
                        if points:
                            panels.setdefault(unit, []).append((f'Configuration A — {app} process tree', points, COLORS['default']))
    if not panels:
        return False
    fig, axes = plt.subplots(len(panels), 1, figsize=(11, len(panels) * 2.4), squeeze=False)
    for ax, (unit, series) in zip(axes[:, 0], panels.items()):
        for index, (name, points, color) in enumerate(series):
            style = '--' if name.startswith('Configuration A') else '-' if name == DISPLAY['coordinated'] else ('-', '-.', ':')[index % 3]
            ax.plot([p[0] for p in points], [p[1] for p in points], marker=('o', 's', '^')[index % 3], markersize=3,
                    linestyle=style, label=name, color=color)
        ylabel = '%' if '(%)' in unit else 'Instructions/cycle' if 'IPC' in unit else 'W' if '(W)' in unit else 'MiB' if 'MiB' in unit else 'Core-equivalents'
        ax.set(title=unit, ylabel=ylabel, xlabel='Recorded window (A/C indices are NOT paired)')
        if unit.startswith('Host socket CPU'):
            ax.set_ylim(0, 105)
        else:
            ax.set_ylim(bottom=0)
        ax.grid(alpha=.15)
        ax.legend(fontsize=7)
    fig.suptitle('Optional resource diagnostics — host, process and cgroup scopes kept separate')
    finish(fig, output, 'resource_telemetry', pairs)
    return True
