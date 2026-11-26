"""Persistent pilot plots: raw window changes, never best-so-far or fabricated gains."""
from pathlib import Path
import matplotlib.pyplot as plt

COLORS = {'default': '#0072B2', 'coordinated': '#D55E00', 'independent': '#009E73'}
STYLES = {'default': '--', 'coordinated': '-', 'independent': '-.'}
MARKERS = {'default': 'o', 'coordinated': 's', 'independent': 'D'}


def finish(fig, output, name):
    fig.tight_layout()
    for suffix in ('png', 'pdf'):
        fig.savefig(Path(output) / f'{name}.{suffix}', dpi=160, bbox_inches='tight')
    plt.close(fig)


def shade_stable(ax, rows):
    windows = [r['window'] for r in rows if r['phase'] == 'stable']
    if windows:
        ax.axvspan(min(windows) - .5, max(windows) + .5, color='gray', alpha=.08)
        ax.axvline(min(windows) - .5, color='gray', linestyle=':', linewidth=1)


def improvement_plots(trajectories, summary, output):
    apps = sorted({r['application'] for r in trajectories})
    runs = sorted({r['run'] for r in trajectories})
    for reference in ('own_baseline', 'configuration_A'):
        anchors = {app: [r for r in summary if r['application'] == app and r['mode'] == 'default'] for app in apps}
        if reference == 'configuration_A' and any(len(rows) != 1 for rows in anchors.values()):
            continue  # A common reference requires exactly one A run, not an arbitrary repetition.
        fig, axes = plt.subplots(len(apps), 1, figsize=(10, 3.5 * len(apps)), squeeze=False)
        for app, ax in zip(apps, axes[:, 0]):
            selected = [r for r in trajectories if r['application'] == app and r['phase'] != 'baseline']
            if not selected:
                ax.text(.5, .5, 'No completed tuning/stable observations', ha='center', transform=ax.transAxes)
                continue
            for run in runs:
                rows = [r for r in selected if r['run'] == run]
                if not rows:
                    continue
                if reference == 'own_baseline':
                    values = [(r['improvement'] - 1) * 100 for r in rows]
                else:
                    anchor = anchors[app][0]
                    minimize = rows[0]['objective'] == 'minimize'
                    values = [((anchor['baseline'] / r['value'] if minimize else r['value'] / anchor['baseline']) - 1) * 100 for r in rows]
                label = rows[0]['mode'] + ' / ' + Path(run).name
                if not rows[0]['completed']:
                    label += ' (incomplete)'
                mode = rows[0]['mode']
                ax.plot([r['window'] for r in rows], values, marker=MARKERS.get(mode, 'o'), markersize=4,
                        linestyle=STYLES.get(mode, '-'), label=label, color=COLORS.get(mode))
            shade_stable(ax, selected)
            ax.axhline(0, color='black', linestyle='--', linewidth=.8)
            ax.set(title=f"{app}: {selected[0]['metric']}", xlabel='Measurement window (shaded = stable phase)',
                   ylabel='Ratio-based improvement (%)')
            ax.grid(alpha=.2)
            ax.legend(fontsize=8)
        fig.suptitle('Per-window improvement vs ' + ('each run\'s own concurrent baseline' if reference == 'own_baseline' else 'Configuration A concurrent baseline'), y=1.01)
        finish(fig, output, 'improvement_per_window' if reference == 'own_baseline' else 'improvement_vs_configuration_A')


def telemetry_plots(results, output):
    fig, axes = plt.subplots(3, 1, figsize=(10, 10))
    for result in results:
        rows = [r for r in result.get('windows', []) if r['phase'] != 'baseline']
        if not rows:
            continue
        windows = [r['window'] for r in rows]
        for ax, metric, label in zip(axes, ('cpu_load_socket0_pct', 'instructions_per_cycle', 'power_socket0_watts'),
                                     ('Socket CPU load (%)', 'Shared IPC', 'Socket power (W)')):
            values = [r['shared'].get(metric) for r in rows]
            if any(v is not None for v in values):
                ax.plot(windows, [float('nan') if v is None else v for v in values], marker='.', label=result['mode'], color=COLORS.get(result['mode']), linestyle=STYLES.get(result['mode'], '-'))
            ax.set(ylabel=label, xlabel='Measurement window')
            ax.grid(alpha=.2)
        for ax in axes:
            shade_stable(ax, rows)
    axes[0].set_ylim(0, 105)
    axes[0].ticklabel_format(axis='y', style='plain', useOffset=False)
    for ax in axes:
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend()
    fig.suptitle('Shared host telemetry (not per-application hardware attribution)')
    finish(fig, output, 'host_telemetry')

    fig, axes = plt.subplots(2, 1, figsize=(10, 7))
    for result in results:
        rows = [r for r in result.get('windows', []) if r['phase'] != 'baseline']
        apps = sorted({app for row in rows for app in row['applications']})
        for app in apps:
            for ax, metric, scale, label in zip(axes, ('cpu_usage_cores', 'memory_current_bytes'),
                                               (1, 1024 ** 2), ('CPU time / wall time (cores)', 'Cgroup memory (MiB)')):
                values = [r['applications'][app].get('cgroup_window', {}).get(metric) for r in rows]
                if any(v is not None for v in values):
                    ax.plot([r['window'] for r in rows], [float('nan') if v is None else v / scale for v in values],
                            marker='.', label=f"{result['mode']} / {app}")
                ax.set(ylabel=label, xlabel='Measurement window')
                ax.grid(alpha=.2)
    for ax in axes:
        ax.set_ylim(bottom=0)
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(fontsize=8)
    fig.suptitle('Per-application cgroup telemetry')
    finish(fig, output, 'application_resources')


def control_plots(results, output):
    """Use pre-window readbacks, not end-of-window decisions that affect the next window."""
    fig, axes = plt.subplots(3, 1, figsize=(11, 10))
    for result in results:
        rows = [r for r in result.get('windows', []) if r['phase'] != 'baseline']
        if not rows:
            continue
        for parameter in ('latency_ns', 'min_granularity_ns', 'wakeup_granularity_ns'):
            values = [r.get('observed_host_start', {}).get(parameter) for r in rows]
            if all(v is not None for v in values):
                axes[0].plot([r['window'] for r in rows], [int(v) / 1000000 for v in values],
                             marker='.', label=f"{result['mode']} / {parameter}")
        for parameter in ('min_perf_pct', 'max_perf_pct'):
            values = [r.get('observed_host_start', {}).get(parameter) for r in rows]
            if all(v is not None for v in values):
                axes[1].plot([r['window'] for r in rows], [int(v) for v in values],
                             marker='.', label=f"{result['mode']} / {parameter}")
        apps = sorted({a for r in rows for a in (r.get('configuration_start') or {}).get('application_updates', {})})
        for app in apps:
            values = [(r.get('configuration_start') or {}).get('application_updates', {}).get(app, {}).get('cpu.weight') for r in rows]
            if all(v is not None for v in values):
                axes[2].plot([r['window'] for r in rows], [int(v) for v in values],
                             marker='.', label=f"{result['mode']} / {app}")
        for ax in axes:
            shade_stable(ax, rows)
    for ax, label in zip(axes, ('Scheduler controls (ms)', 'Intel P-state (%)', 'Cgroup CPU weight')):
        ax.set(ylabel=label, xlabel='Measurement window')
        ax.grid(alpha=.2)
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(fontsize=7, ncol=2)
    fig.suptitle('Effective controls at window start (decisions take effect at boundaries)')
    finish(fig, output, 'control_trajectory')
