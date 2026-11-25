"""Offline CSV summaries and optional plots. Never starts workloads or provider clients."""
import argparse
import csv
import json
from pathlib import Path
from statistics import median
from .controls import decode


def export(files, output, plots=False):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    trajectories, summary, decisions, evaluations = [], [], [], []
    for filename in files:
        result = decode(Path(filename).read_text())
        mode = result['mode']
        run_id = str(Path(filename).resolve().parent)
        for row in result.get('windows', []):
            for app, observation in row['applications'].items():
                trajectories.append(dict(run=run_id, completed=result['completed'], mode=mode, application=app,
                                         phase=row['phase'], window=row['window'], start=row['start'], end=row['end'],
                                         metric=observation['metric'], value=observation['current'],
                                         improvement=observation.get('improvement', ''),
                                         constraint_violation=observation.get('constraint_violation', ''),
                                         significant_regression=observation.get('significant_regression', '')))
        for app in result.get('applications', []):
            selected = [r for r in trajectories if r['run'] == run_id and r['application'] == app['id'] and r['phase'] == 'stable']
            if not selected:
                continue
            value = median(r['value'] for r in selected)
            baseline = app['baseline']
            factor = baseline / value if app['objective'] == 'minimize' else value / baseline
            bound = baseline if app['bound'] == 'default' else app['bound']
            violated = value > bound if app['objective'] == 'minimize' else value < bound
            tolerance = result['config'].get('regression_tolerance', 0.05)
            regressed = value > baseline * (1 + tolerance) if app['objective'] == 'minimize' else value < baseline * (1 - tolerance)
            summary.append(dict(run=run_id, mode=mode, application=app['id'], completed=result['completed'],
                                metric=app['metric'], stable_median=value, baseline=baseline, improvement=factor,
                                bound=bound, constraint_violation=violated, stable_regression=regressed,
                                measured_windows=len(selected), expected_windows=result['config'].get('stable_windows', 3)))
        for controller, records in result.get('decisions', {}).items():
            for record in records:
                decisions.append(dict(run=run_id, mode=mode, controller=controller, timestamp=record['timestamp'],
                                      role=record['role'], response_seconds=record.get('response_time'),
                                      tokens=json.dumps(record.get('token_metrics')), error=record.get('error', ''),
                                      proposal=json.dumps(record['proposal'])))
    for run in sorted({r['run'] for r in summary}):
        rows = [r for r in summary if r['run'] == run]
        complete = len(rows) == 2 and all(r['completed'] and r['measured_windows'] == r['expected_windows'] for r in rows)
        evaluations.append(dict(run=run, mode=rows[0]['mode'], complete=complete,
                                experimental_success=complete and not any(r['stable_regression'] for r in rows),
                                all_user_bounds_satisfied=complete and not any(r['constraint_violation'] for r in rows)))
    for name, rows in (('trajectories', trajectories), ('stable', summary), ('decisions', decisions), ('evaluation', evaluations)):
        with (output / f'{name}.csv').open('w', newline='') as stream:
            if rows:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
    if plots:
        import matplotlib.pyplot as plt
        for app in sorted({r['application'] for r in trajectories}):
            fig, axes = plt.subplots(1, 3, figsize=(15, 4))
            selected = [r for r in summary if r['application'] == app]
            axes[0].bar([f"{r['mode']}\n{Path(r['run']).name}" + (' (incomplete)' if not r['completed'] else '') for r in selected], [r['stable_median'] for r in selected])
            axes[0].set_title(f'{app}: stable window-metric median')
            for run in sorted({r['run'] for r in trajectories}):
                rows = [r for r in trajectories if r['application'] == app and r['run'] == run and r['phase'] != 'baseline']
                if not rows:
                    continue
                label = f"{rows[0]['mode']} / {Path(run).name}" + (' (incomplete)' if not rows[0]['completed'] else '')
                axes[1].plot([r['window'] for r in rows], [r['value'] for r in rows], label=label)
                axes[2].plot([r['window'] for r in rows], [r['improvement'] for r in rows], label=label)
                violations = [r for r in rows if r['constraint_violation']]
                axes[1].scatter([r['window'] for r in violations], [r['value'] for r in violations], marker='x')
            axes[1].set_title('Trajectory (x = bound violation)')
            axes[2].set_title('Default-relative factor')
            axes[2].axhline(1, color='gray', linestyle='--')
            for ax in axes[1:]:
                ax.set_xlabel('Window')
                ax.legend(fontsize=7)
            fig.tight_layout()
            fig.savefig(output / f'{app}.png')
            plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results', nargs='+')
    parser.add_argument('--output', required=True)
    parser.add_argument('--plots', action='store_true')
    args = parser.parse_args()
    export(args.results, args.output, args.plots)


if __name__ == '__main__':
    main()
