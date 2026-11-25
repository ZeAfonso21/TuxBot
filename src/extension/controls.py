"""Small allowlisted cgroup-v2 actuator with readback and transactional recovery."""
from pathlib import Path
import json
import os
import threading
import time


class Control:
    def __init__(self, path, minimum, maximum, kind="integer"):
        self.path = Path(path)
        self.minimum, self.maximum, self.kind = minimum, maximum, kind

    def schema(self):
        result = dict(type=self.kind, minimum=self.minimum, maximum=self.maximum)
        if self.kind == "cpu.max":
            result["format"] = "'max 100000' or '<quota> 100000'; quota >= 10000 microseconds"
        return result

    def validate(self, value):
        if self.kind == "cpu.max":
            if not isinstance(value, str):
                raise ValueError("cpu.max must be a string")
            fields = value.split()
            if len(fields) != 2 or fields[1] != "100000":
                raise ValueError("Only a fixed 100000us period is supported")
            if fields[0] != "max":
                if not fields[0].isdigit() or not self.minimum <= int(fields[0]) <= self.maximum:
                    raise ValueError("Unsafe CPU quota")
            return " ".join(fields)
        if type(value) is not int or not self.minimum <= value <= self.maximum:
            raise ValueError(f"Expected integer in [{self.minimum}, {self.maximum}]")
        return str(value)

    def read(self):
        return self.path.read_text().strip()

    def write(self, value):
        self.path.write_text(str(value) + "\n")


class Cgroups:
    """Use an explicitly delegated, empty non-root v2 subtree; never mount or sudo."""
    def __init__(self, root, ids):
        self.root = Path(root).resolve()
        mount = Path('/sys/fs/cgroup').resolve()
        if self.root == mount or mount not in self.root.parents:
            raise ValueError("Use a delegated subtree beneath /sys/fs/cgroup")
        self.paths = {app: self.root / app for app in ids}
        self.created = []
        self.original_subtree = None

    def create(self):
        if not (self.root / 'cgroup.controllers').is_file():
            raise RuntimeError("Delegated cgroup v2 root must already exist")
        if (self.root / 'cgroup.procs').read_text().strip():
            raise RuntimeError("Delegated parent must contain no processes")
        if any(entry.is_dir() for entry in self.root.iterdir()):
            raise RuntimeError('Use an exclusive experiment root with no existing child cgroups')
        self.original_subtree = (self.root / 'cgroup.subtree_control').read_text().split()
        available = (self.root / 'cgroup.controllers').read_text().split()
        selected = [x for x in ('cpu', 'memory', 'io') if x in available]
        if 'cpu' not in selected:
            raise RuntimeError("CPU controller delegation required")
        (self.root / 'cgroup.subtree_control').write_text(' '.join('+' + x for x in selected))
        for path in self.paths.values():
            if path.exists():
                raise RuntimeError(f"Refusing to reuse potentially populated cgroup: {path}")
            path.mkdir()
            self.created.append(path)
            if not (path / 'cgroup.kill').is_file() or not os.access(path / 'cgroup.kill', os.W_OK):
                raise RuntimeError('Writable cgroup.kill is required for safe descendant cleanup')

    def await_empty(self, timeout=10):
        deadline = time.monotonic() + timeout
        pending = list(self.created)
        while pending and time.monotonic() < deadline:
            pending = [p for p in pending if 'populated 1' in (p / 'cgroup.events').read_text()]
            if pending:
                time.sleep(0.05)
        return [f'{p}: descendants remain populated after cleanup' for p in pending]

    def cleanup(self):
        errors = []
        for path in reversed(self.created):
            try:
                path.rmdir()  # populated groups fail visibly; never migrate unrelated PIDs
            except OSError as exc:
                errors.append(str(exc))
        if self.original_subtree is not None:
            try:
                current = (self.root / 'cgroup.subtree_control').read_text().split()
                changes = ['-' + x for x in current if x not in self.original_subtree]
                if changes:
                    (self.root / 'cgroup.subtree_control').write_text(' '.join(changes))
            except OSError as exc:
                errors.append(str(exc))
        return errors


def cgroup_controls(path, policy):
    """Memory high is opt-in with an operator-supplied safe floor; no hard OOM limit."""
    candidates = {
        'cpu.weight': Control(path / 'cpu.weight', 1, 10000),
        'cpu.max': Control(path / 'cpu.max', 10000, 102400000, 'cpu.max'),
    }
    if 'memory_high_min_bytes' in policy:
        floor = policy['memory_high_min_bytes']
        ceiling = policy['memory_high_max_bytes']
        if type(floor) is not int or type(ceiling) is not int or floor < 67108864 or ceiling < floor:
            raise ValueError("Memory high requires safe integer byte bounds")
        candidates['memory.high'] = Control(path / 'memory.high', floor, ceiling)
    # io.weight depends on the block scheduler and needs device-specific verification.
    return {k: v for k, v in candidates.items() if v.path.is_file()}


class Actuator:
    def __init__(self, applications, host=None):
        self.applications, self.host = applications, host or {}
        self.lock = threading.RLock()
        self.initial = self.snapshot()
        self.audit = []
        self.poisoned = False

    def schema(self):
        return dict(application_updates={a: {k: c.schema() for k, c in controls.items()}
                                         for a, controls in self.applications.items()},
                    host_updates={k: c.schema() for k, c in self.host.items()})

    def snapshot(self):
        return dict(application_updates={a: {k: c.read() for k, c in controls.items()}
                                         for a, controls in self.applications.items()},
                    host_updates={k: c.read() for k, c in self.host.items()})

    def validate(self, proposal):
        if not isinstance(proposal, dict) or set(proposal) - {'application_updates', 'host_updates', 'reasoning'}:
            raise ValueError("Unknown proposal fields")
        if 'reasoning' in proposal and not isinstance(proposal['reasoning'], str):
            raise ValueError("reasoning must be text")
        apps, host = proposal.get('application_updates', {}), proposal.get('host_updates', {})
        if not isinstance(apps, dict) or not isinstance(host, dict):
            raise ValueError("Updates must be objects")
        writes = []
        for app, updates in apps.items():
            if app not in self.applications or not isinstance(updates, dict):
                raise ValueError("Unauthorized application")
            for name, value in updates.items():
                if name not in self.applications[app]:
                    raise ValueError("Unavailable cgroup control")
                control = self.applications[app][name]
                writes.append((control, control.validate(value)))
        for name, value in host.items():
            if name not in self.host:
                raise ValueError("Unauthorized host control")
            control = self.host[name]
            writes.append((control, control.validate(value)))
        state = self.snapshot()['host_updates']
        state.update(host)
        if 'min_perf_pct' in state and 'max_perf_pct' in state and int(state['min_perf_pct']) > int(state['max_perf_pct']):
            raise ValueError("min_perf_pct exceeds max_perf_pct")
        paths = [c.path for c, _ in writes]
        if len(paths) != len(set(paths)):
            raise ValueError("Conflicting duplicate control paths")
        return writes

    def _ordered(self, writes):
        # Lower minimum before decreasing maximum, raise maximum before raising minimum.
        return sorted(writes, key=lambda item: 0 if item[0] is self.host.get('min_perf_pct') and int(item[1]) < int(item[0].read()) else 2 if item[0] is self.host.get('min_perf_pct') else 1)

    def apply(self, proposal):
        with self.lock:
            if self.poisoned:
                raise RuntimeError('Actuator disabled after failed rollback; restore manually')
            writes = self._ordered(self.validate(proposal))
            before = [(c, c.read()) for c, _ in writes]
            try:
                for control, value in writes:
                    control.write(value)
                    if control.read() != value:
                        raise RuntimeError(f"Readback mismatch: {control.path}")
            except BaseException as exc:
                errors = self._restore_values(before)
                self.audit.append(dict(proposal=proposal, error=str(exc), rollback_errors=errors, effective=self.snapshot()))
                if errors:
                    self.poisoned = True
                    raise RuntimeError(f"Update failed; rollback also failed: {errors}") from exc
                raise
            state = self.snapshot()
            self.audit.append(dict(proposal=proposal, effective=state))
            return state

    def _restore_values(self, values):
        errors = []
        for control, value in self._ordered(values):
            try:
                control.write(value)
                if control.read() != value:
                    raise RuntimeError("restoration readback mismatch")
            except Exception as exc:
                errors.append(f"{control.path}: {exc}")
        return errors

    def restore(self):
        with self.lock:
            values = [(c, self.initial['application_updates'][a][k]) for a, controls in self.applications.items() for k, c in controls.items()]
            values += [(c, self.initial['host_updates'][k]) for k, c in self.host.items()]
            return self._restore_values(values)

    def set_parameters(self, parameters):
        # The legacy startup/reset receives an empty flat schema. Never interpret it as authority.
        if parameters:
            raise ValueError("Flat legacy writes are disabled for extension sessions")
        return True


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def decode(text):
    return json.loads(text, object_pairs_hook=unique_object)
