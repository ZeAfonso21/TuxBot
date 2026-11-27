"""Validated shared A reference; no actuation or provider access."""
from statistics import mean
from .evaluation import load_run
from .model import positive


def initial_mean_reference(run):
    rows = [w for w in run['windows'] if w['phase'] == 'baseline']
    if len(rows) != 3 or any(v is None for w in rows for v in w['values'].values()):
        raise ValueError('Shared reference requires exactly three complete concurrent A baseline windows')
    return {app: mean(positive(w['values'][app]) for w in rows) for app in run['apps']}


def stable_mean_reference(run):
    """Use every recorded stable window; incomplete references fail rather than shrink."""
    rows = [w for w in run['windows'] if w['phase'] == 'stable']
    expected = run['data'].get('config', {}).get('stable_windows')
    if not rows or (expected is not None and len(rows) != expected) or any(
        v is None for w in rows for v in w['values'].values()
    ):
        raise ValueError('Shared reference requires the complete joint A stable phase')
    return {app: mean(positive(w['values'][app]) for w in rows) for app in run['apps']}


def load_reference(filename, apps, conditions, policy='stable_mean', window_seconds=None, warmup_seconds=None):
    run = load_run(filename)
    data = run['data']
    if run['mode'] != 'default' or run['dedicated_cgroups'] is not False or data.get('completed') is not True:
        raise ValueError('Reference must be a completed, no-cgroup, untuned A run')
    if any(data.get(key) for key in ('decisions', 'controllers', 'actuation_audit')):
        raise ValueError('A reference contains tuning/actuation records')
    specs = {a.id: dict(metric=a.metric, objective=a.objective) for a in apps}
    if run['apps'] != specs or not conditions or data['config'].get('workload_conditions') != conditions:
        raise ValueError('Reference workload conditions, metrics or objectives differ')
    for key, expected in (('window_seconds', window_seconds), ('warmup_seconds', warmup_seconds)):
        if expected is not None and data['config'].get(key) != expected:
            raise ValueError(f'A/C {key} differs; collect a matching A reference')
    if policy not in ('initial_mean', 'stable_mean'):
        raise ValueError('Shared reference policy must be initial_mean or stable_mean')
    initial = data.get('initial_host_observations', {})
    for window in run['windows']:
        for field in ('observed_host_start', 'observed_host_end'):
            current = window['raw'].get(field, {})
            if any(k in current and str(current[k]) != str(v) for k, v in initial.items()):
                raise ValueError('A host controls changed during reference measurement')
    phase = 'stable' if policy == 'stable_mean' else 'baseline'
    return dict(source=run['source'], sha256=run['sha256'], policy=policy,
                aggregation='mean of complete joint A stable windows' if policy == 'stable_mean' else 'mean of first three concurrent A windows',
                windows=[w['window'] for w in run['windows'] if w['phase'] == phase],
                values=(stable_mean_reference if policy == 'stable_mean' else initial_mean_reference)(run))
