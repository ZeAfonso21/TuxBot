"""Read-only A/C evaluation. References are recorded A aggregates, never tuner rewards.

No optimizer, provider client, process launcher or privileged interface is imported.
"""
import hashlib
import math
from pathlib import Path
from statistics import mean, median
from .controls import decode

DISPLAY = {'default': 'Configuration A — Untuned', 'coordinated': 'Configuration C — Coordinated'}


def improvement(reference, current, objective):
    """Ordinary latency reduction / throughput increase (%), NOT ratio speedup."""
    if type(reference) not in (int, float) or not math.isfinite(reference) or reference <= 0:
        raise ValueError('Configuration A reference must be finite and strictly positive')
    if objective not in ('minimize', 'maximize'):
        raise ValueError('Unknown metric direction')
    if current is None:
        return None
    if type(current) not in (int, float) or not math.isfinite(current) or current < 0:
        raise ValueError('Current metric must be finite and nonnegative')
    change = (current - reference) / reference * 100
    return -change if objective == 'minimize' else change


def has_workload_cgroups(data):
    """Return evidence, not an assumption based on an A/default label."""
    snapshots = [data.get('initial_configuration') or {}]
    snapshots += [row.get(field) or {} for row in data.get('windows', []) for field in ('configuration_start', 'configuration_end')]
    configured = any(any((snapshot.get('application_updates') or {}).values()) for snapshot in snapshots)
    observed = any(any(app.get(field) for field in ('cgroup_before', 'cgroup_after', 'cgroup_window'))
                   or (app.get('resource_scope') or {}).get('kind') == 'cgroup'
                   for row in data.get('windows', []) for app in (row.get('applications') or {}).values() if isinstance(app, dict))
    declared = (data.get('provenance') or {}).get('dedicated_workload_cgroups')
    if configured or observed:
        if declared is False:
            raise ValueError('Contradictory provenance: no-cgroup declaration but workload cgroup data present')
        return True
    return declared if type(declared) is bool else None


def load_run(filename):
    path = Path(filename).resolve()
    content = path.read_text()
    data = decode(content)
    config = data.get('config', {})
    if (data.get('provenance') or {}).get('concurrent_workloads') is False:
        raise ValueError('Sequential/single-workload measurements cannot serve as concurrent A/C data')
    apps = data.get('applications') or config.get('applications', [])
    if len(apps) != 2 or len({a['id'] for a in apps}) != 2:
        raise ValueError(f'{path}: expected exactly two distinct applications')
    applications = {a['id']: dict(metric=a['metric'], objective=a['objective']) for a in apps}
    if any(a['objective'] not in ('minimize', 'maximize') for a in applications.values()):
        raise ValueError('Unknown application objective')
    notes, windows, seen = [], [], set()
    for raw in data.get('windows', []):
        number, start, end = raw.get('window'), raw.get('start'), raw.get('end')
        if type(number) is not int or number in seen:
            raise ValueError('Measurement window IDs must be unique integers within a run')
        seen.add(number)
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end)) or end <= start:
            raise ValueError(f'Window {number}: invalid common endpoints')
        phase = raw.get('phase', 'measurement')
        if phase not in ('baseline', 'tuning', 'stable', 'warmup', 'measurement'):
            notes.append(f'Window {number}: unknown phase {phase!r}; no steady-state inference made')
            phase = 'measurement'
        values = {}
        observations = raw.get('applications') or {}
        if not isinstance(observations, dict):
            raise ValueError(f'Window {number}: applications must be a measurement object')
        for app, spec in applications.items():
            observation = observations.get(app)
            if not isinstance(observation, dict):
                values[app] = None
                notes.append(f'Window {number}: missing {app}; not replaced with zero')
                continue
            if observation.get('metric') != spec['metric'] or observation.get('objective', spec['objective']) != spec['objective']:
                raise ValueError(f'Window {number}: metric/direction changed for {app}')
            endpoints = observation.get('raw', {})
            if ('window_start' in endpoints or 'window_end' in endpoints) and (
                endpoints.get('window_start') != start or endpoints.get('window_end') != end
            ):
                raise ValueError(f'Window {number}: {app} endpoints do not match the joint window')
            value = observation.get('current')
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
                notes.append(f'Window {number}: invalid {app} value excluded')
                value = None
            values[app] = value
            if value is None:
                notes.append(f'Window {number}: unavailable {app} metric')
        windows.append(dict(window=number, phase=phase, start=start, end=end, values=values, raw=raw))
    windows.sort(key=lambda w: w['start'])
    if any(b['start'] < a['end'] for a, b in zip(windows, windows[1:])):
        raise ValueError('Overlapping measurement windows within a run')
    measured = [w for w in windows if w['phase'] not in ('warmup', 'baseline')]
    gaps = sorted(set(range(min((w['window'] for w in measured), default=0), max((w['window'] for w in measured), default=-1) + 1)) - {w['window'] for w in measured})
    if gaps:
        notes.append(f'Missing measurement window IDs: {gaps}')
    stable = [w for w in windows if w['phase'] == 'stable']
    expected = config.get('stable_windows')
    if expected is not None and len(stable) != expected:
        notes.append(f'Stable count differs from metadata: {len(stable)} recorded, {expected} expected')
    if data.get('completed') is not True:
        notes.append('Producer marks this run incomplete')
    return dict(source=str(path), sha256=hashlib.sha256(content.encode()).hexdigest(), data=data,
                mode=data.get('mode'), apps=applications, windows=windows, notes=notes,
                dedicated_cgroups=has_workload_cgroups(data),
                data_kind=data.get('data_kind', config.get('data_kind', 'measured')))


def stable_aggregate(run, aggregation='median'):
    """Use complete *joint* stable windows; never select each app's best/mismatched window."""
    windows = [w for w in run['windows'] if w['phase'] == 'stable' and all(v is not None for v in w['values'].values())]
    all_stable = [w for w in run['windows'] if w['phase'] == 'stable']
    if len(windows) != len(all_stable):
        run['notes'].append('Incomplete joint stable windows excluded from both app aggregates')
    return ({app: (mean if aggregation == 'mean' else median)(w['values'][app] for w in windows) for app in run['apps']} if windows else {},
            [w['window'] for w in windows])


def check_conditions(a, c, review):
    left = a['data'].get('config', {}).get('workload_conditions')
    right = c['data'].get('config', {}).get('workload_conditions')
    if left is not None or right is not None:
        if not left or left != right or set(left) != set(a['apps']):
            raise ValueError('A/C workload conditions are missing or differ; cannot use this A reference')
        return dict(method='matching recorded workload_conditions', conditions=left)
    if review.get('conditions_verified') is True and review.get('conditions_evidence') and set(review.get('workload_conditions', {})) == set(a['apps']):
        return dict(method='explicit offline review (not an embedded runtime fingerprint)',
                    conditions=review['workload_conditions'], evidence=review['conditions_evidence'])
    raise ValueError('Workload equivalence is unrecorded: provide matching workload_conditions or an explicit reviewed pair manifest')


def actual_config(window, notes):
    raw = window['raw']
    config = raw.get('configuration_start')
    end = raw.get('configuration_end')
    if not isinstance(config, dict):
        if not isinstance(raw.get('observed_host_start'), dict):
            return None
        config = dict(application_updates={}, host_updates=raw['observed_host_start'])
        end = None  # only the host's start snapshot is recorded; do not infer app histories
    if end is not None and end != config:
        notes.append(f'Window {window["window"]}: controls changed within the window; omitted from constant-configuration step series')
        return None
    host = config.get('host_updates') or {}
    applications = config.get('application_updates') or {}
    if not isinstance(host, dict) or not isinstance(applications, dict):
        notes.append(f'Window {window["window"]}: invalid readback maps omitted')
        return None
    observed = raw.get('observed_host_start')
    if observed is not None:
        if any(str(observed[k]) != str(value) for k, value in host.items() if k in observed):
            notes.append(f'Window {window["window"]}: conflicting host readbacks; host series omitted')
            host = {}
        else:
            host = observed
    return dict(application_updates=applications, host_updates=host)


def control_series(run):
    """Only actual C readbacks; proposals, rewards and resource telemetry are never controls."""
    notes, snapshots = [], []
    for window in run['windows']:
        if window['phase'] not in ('baseline', 'warmup'):
            snapshots.append((window, actual_config(window, notes)))
    initial = run['data'].get('initial_configuration') or {}
    keys = set()
    for _, snapshot in snapshots:
        if snapshot:
            keys.update(('host', '', name) for name in snapshot.get('host_updates', {}))
            keys.update(('application', app, name) for app, values in snapshot.get('application_updates', {}).items() if isinstance(values, dict) for name in values)
    series = []
    telemetry_names = {'memory.current', 'cpu.stat', 'io.stat', 'cpu_usage_cores', 'memory_current_bytes'}
    for scope, app, parameter in sorted(keys):
        if scope == 'application' and app not in run['apps']:
            notes.append(f'Unknown cgroup application {app!r}; no scope attribution invented')
            continue
        if parameter in telemetry_names or parameter.endswith('.pressure'):
            notes.append(f'{parameter} is telemetry, not a tunable; excluded from control plot')
            continue
        def get(snapshot):
            if not snapshot:
                return None
            values = (snapshot.get('host_updates') or {}) if scope == 'host' else (snapshot.get('application_updates') or {}).get(app, {})
            return values.get(parameter) if isinstance(values, dict) else None
        original = get(initial)
        points = [dict(window=w['window'], phase=w['phase'], value=get(snapshot)) for w, snapshot in snapshots]
        observed = {str(p['value']) for p in points if p['value'] is not None}
        changed = len(observed) > 1 or (original is not None and any(v != str(original) for v in observed))
        series.append(dict(scope=scope, application=app, parameter=parameter, initial=original,
                           changed=changed, points=points))
    # For an application-specific knob changed in either cgroup, show its separately read comparator too.
    changed_app_parameters = {s['parameter'] for s in series if s['scope'] == 'application' and s['changed']}
    selected = [s for s in series if s['changed'] or (s['scope'] == 'application' and s['parameter'] in changed_app_parameters)]
    omitted = [f"{s['scope']}/{s['application']}/{s['parameter']}" for s in series if s not in selected]
    if omitted:
        notes.append('Unmodified control series omitted: ' + ', '.join(omitted))
    if not selected:
        notes.append('No modified actual control history available; proposed settings are not substituted')
    notes.append('Steps use measurement-window-start readbacks, not exact write timestamps; gaps are not filled')
    return selected, notes


def nondominated(points):
    """Observed frontier among synchronized C points AND the untuned origin; not a global optimum."""
    values = [p['improvements'] for p in points]
    result = []
    for i, value in enumerate(values):
        competitors = values[:i] + values[i + 1:] + [[0, 0]]
        if not any(all(x >= y for x, y in zip(other, value)) and any(x > y for x, y in zip(other, value)) for other in competitors):
            result.append(i)
    return result


def evaluate_pair(a, c, pair_id='pair-1', review=None, allow_legacy_a=False):
    review = review or {}
    if a['mode'] != 'default' or c['mode'] != 'coordinated':
        raise ValueError('Primary evaluation requires untuned/default A and coordinated C, never a tuned reference')
    if a['data'].get('completed') is not True:
        raise ValueError('An incomplete/failed run cannot serve as the Configuration A reference')
    if any(a['data'].get(key) for key in ('decisions', 'controllers', 'actuation_audit')):
        raise ValueError('Configuration A contains tuner/actuation records; it is not an untuned reference')
    initial_host = a['data'].get('initial_host_observations')
    if initial_host:
        for window in a['windows']:
            for field in ('observed_host_start', 'observed_host_end'):
                observed = window['raw'].get(field, {})
                if any(k in observed and str(observed[k]) != str(v) for k, v in initial_host.items()):
                    raise ValueError('Configuration A host controls changed from its captured initial state')
    if c['dedicated_cgroups'] is False:
        raise ValueError('Configuration C declares no workload cgroups; this is not the coordinated protocol')
    if a['apps'] != c['apps']:
        raise ValueError('A/C application identifiers, metrics or objectives differ')
    if a['data_kind'] != c['data_kind']:
        raise ValueError('Synthetic fixtures must not be mixed with measured experiment results')
    for key in ('window_seconds', 'warmup_seconds'):
        left, right = a['data'].get('config', {}).get(key), c['data'].get('config', {}).get(key)
        if left is not None and right is not None and left != right:
            raise ValueError(f'A/C {key} differs; the reference is not comparable')
    if a['dedicated_cgroups'] is not False and not allow_legacy_a:
        raise ValueError('Configuration A has dedicated workload cgroups or unknown provenance; strict no-cgroup A is required. Use --allow-legacy-a only for explicitly labelled historical diagnostics.')
    historical = a['dedicated_cgroups'] is not False
    conditions = check_conditions(a, c, review)
    reference, a_windows = stable_aggregate(a)
    reference_windows = a_windows
    reference_policy = review.get('reference_policy', 'initial_mean' if c['data'].get('baseline_reference') else 'stable_median')
    if c['data'].get('baseline_reference') and reference_policy != 'initial_mean':
        raise ValueError('Report must retain the shared A reference actually used by the tuner')
    if reference_policy not in ('stable_median', 'initial_mean'):
        raise ValueError('Unknown A reference policy')
    if reference_policy == 'initial_mean':
        # EXTENSION: the requested A reference also governs C's actual tuning targets.
        from .baseline import initial_mean_reference
        reference = initial_mean_reference(a)
        reference_windows = [w['window'] for w in a['windows'] if w['phase'] == 'baseline']
        proof = c['data'].get('baseline_reference', {})
        if proof.get('sha256') != a['sha256'] or proof.get('values') != reference:
            raise ValueError('C did not record the same A initial-mean tuning reference')
    aggregate = 'mean' if reference_policy == 'initial_mean' else 'median'
    stable_c, c_windows = stable_aggregate(c, aggregate)
    reference_description = ('fixed A initial-three-window arithmetic mean' if reference_policy == 'initial_mean'
                             else 'fixed A complete joint stable-window median')
    for app, value in reference.items():
        improvement(value, value, a['apps'][app]['objective'])  # reject zero/invalid A references
    notes = a['notes'] + c['notes']
    if not reference:
        notes.append('No complete joint A stable windows: performance figures cannot be generated; no fallback baseline invented')
    if not stable_c:
        notes.append('No complete joint C stable windows: stable summary unavailable')
    if historical:
        notes.append('HISTORICAL ONLY: A used dedicated default-valued cgroups (or lacks no-cgroup proof); not the requested no-cgroup baseline')
    order = {'latency_p99_ms': 0, 'throughput_mib_s': 1}
    apps = sorted(a['apps'], key=lambda app: order.get(a['apps'][app]['metric'], 2))
    curves = []
    for window in c['windows']:
        if window['phase'] == 'warmup':
            continue
        changes = [improvement(reference[app], window['values'][app], a['apps'][app]['objective']) if reference else None for app in apps]
        curves.append(dict(window=window['window'], phase=window['phase'], start=window['start'], end=window['end'],
                           current=[window['values'][app] for app in apps], improvements=changes))
    joint = [row for row in curves if all(v is not None for v in row['improvements'])]
    frontier = nondominated(joint)
    summary = [dict(application=app, metric=a['apps'][app]['metric'], objective=a['apps'][app]['objective'],
                    reference=reference.get(app), coordinated=stable_c.get(app),
                    improvement_pct=improvement(reference[app], stable_c[app], a['apps'][app]['objective']) if reference and stable_c else None)
               for app in apps]
    controls, control_notes = control_series(c)
    notes.extend(control_notes)
    return dict(id=pair_id, apps=apps, specs=a['apps'], a=a, c=c, historical=historical,
                synthetic=a['data_kind'] == 'synthetic' or c['data_kind'] == 'synthetic', conditions=conditions,
                reference=reference, reference_policy=reference_policy, reference_description=reference_description,
                reference_windows=reference_windows, stable_aggregation=aggregate,
                a_stable_windows=a_windows, c_stable_windows=c_windows,
                curves=curves, pareto=joint, frontier_indices=frontier, summary=summary, controls=controls, notes=notes)


def load_pairs(files=None, manifest=None, allow_legacy_a=False):
    """Run pairing must be explicit for repetitions. A and C window indices are never paired."""
    if manifest:
        path = Path(manifest).resolve()
        data = decode(path.read_text())
        definitions = data['pairs']
        root = path.parent
    else:
        runs = [load_run(p) for p in files or []]
        a = [r for r in runs if r['mode'] == 'default']
        c = [r for r in runs if r['mode'] == 'coordinated']
        if len(runs) != len(a) + len(c):
            raise ValueError('This primary report accepts A and C only; other modes are not silently discarded')
        if len(a) != 1 or len(c) != 1:
            raise ValueError('Provide exactly one A/C pair or --pairs with explicit independent run pairings')
        definitions = [dict(id='pair-1', a=a[0]['source'], c=c[0]['source'])]
        root = Path.cwd()
    if not definitions:
        raise ValueError('Empty pair manifest')
    pairs, seen_a, seen_c, seen_ids = [], set(), set(), set()
    for definition in definitions:
        a, c = load_run(root / definition['a']), load_run(root / definition['c'])
        if definition['id'] in seen_ids or a['sha256'] in seen_a or c['sha256'] in seen_c:
            raise ValueError('Repeated artifacts/pair IDs are not independent experiment replications')
        seen_ids.add(definition['id'])
        seen_a.add(a['sha256'])
        seen_c.add(c['sha256'])
        pair = evaluate_pair(a, c, definition['id'], definition, allow_legacy_a)
        if pairs and (pair['reference_policy'] != pairs[0]['reference_policy'] or pair['specs'] != pairs[0]['specs'] or pair['conditions']['conditions'] != pairs[0]['conditions']['conditions']):
            raise ValueError('Different workload pairs/conditions must be evaluated separately')
        pairs.append(pair)
    if len(pairs) > 1 and not all(d.get('independent_repetition') is True for d in definitions):
        raise ValueError('Multiple pairs require explicit independent_repetition=true declarations; windows are not replications')
    return pairs


def repetition_summary(pairs):
    rows = []
    for index, app in enumerate(pairs[0]['apps']):
        values = [p['summary'][index]['improvement_pct'] for p in pairs if p['summary'][index]['improvement_pct'] is not None]
        rows.append(dict(application=app, n_pairs=len(values),
                         median_improvement_pct=median(values) if values else None,
                         minimum_improvement_pct=min(values) if values else None,
                         maximum_improvement_pct=max(values) if values else None,
                         variability='observed paired-run range, not a confidence interval',
                         statistical_unit='A/C run pair after the declared within-run aggregation'))
    return rows
