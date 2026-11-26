"""Eight logical paper controls: fixed known interfaces only, no guessed EEVDF aliases."""
from pathlib import Path
import os
from .controls import Control

# Logical name, original/known interfaces, conservative experimental range.
HOST = {
    'min_granularity_ns': (['/sys/kernel/debug/sched/min_granularity_ns', '/proc/sys/kernel/sched_min_granularity_ns'], 100000, 100000000),
    'latency_ns': (['/sys/kernel/debug/sched/latency_ns', '/proc/sys/kernel/sched_latency_ns'], 1000000, 1000000000),
    'wakeup_granularity_ns': (['/sys/kernel/debug/sched/wakeup_granularity_ns', '/proc/sys/kernel/sched_wakeup_granularity_ns'], 0, 100000000),
    'migration_cost_ns': (['/sys/kernel/debug/sched/migration_cost_ns', '/proc/sys/kernel/sched_migration_cost_ns'], 0, 100000000),
    'napi_busy_poll': (['/proc/sys/net/core/busy_poll'], 0, 1000),
    'min_perf_pct': (['/sys/devices/system/cpu/intel_pstate/min_perf_pct'], 0, 100),
    'max_perf_pct': (['/sys/devices/system/cpu/intel_pstate/max_perf_pct'], 1, 100),
}


def limit_host(controls, limits):
    """Narrow verified ranges for a pilot; configuration cannot broaden the allowlist."""
    for name, bounds in limits.items():
        if name not in controls or not isinstance(bounds, list) or len(bounds) != 2 or any(type(v) is not int for v in bounds):
            raise ValueError('Host limits require an active control and two integer bounds')
        control = controls[name]
        low, high = max(control.minimum, bounds[0]), min(control.maximum, bounds[1])
        if low > high:
            raise ValueError('Host limits have no overlap with the verified range')
        control.minimum, control.maximum = low, high


def resolve_host(approved):
    """Called only by the authorized runner. Report absent/unapproved controls explicitly."""
    unknown = set(approved) - set(HOST) - {'cstate_max'}
    if unknown:
        raise ValueError(f'Unknown host controls: {unknown}')
    active, report = {}, {}
    for name, (paths, minimum, maximum) in HOST.items():
        entry = dict(scope='host', candidates=paths, approved=name in approved, available=False)
        for path in paths:
            file = Path(path)
            if file.is_file():
                try:
                    value = int(file.read_text().strip())
                except (OSError, ValueError) as exc:
                    entry['error'] = str(exc)
                    continue
                entry.update(available=True, path=path, initial=value, writable=os.access(file, os.W_OK))
                if name in approved and entry['writable']:
                    active[name] = Control(file, minimum, maximum)
                break
        report[name] = entry
    report['cstate_max'] = dict(scope='per-CPU idle-state masks', available=False,
                               reason='No scalar reversible interface; legacy name-based masks are not semantic verification. Excluded.')
    # Both endpoints must be readable for validation, even if only one was requested.
    if any(k in active for k in ('min_perf_pct', 'max_perf_pct')):
        if not all(k in active for k in ('min_perf_pct', 'max_perf_pct')):
            raise ValueError('Approve both Intel P-state percentage endpoints together')
    return active, report
