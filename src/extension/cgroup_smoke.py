"""Small real-cgroup lifecycle test; no benchmark, provider request, or host-knob writes."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import uuid
from .controls import Actuator, Cgroups, cgroup_controls
from .host import resolve_host


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorize-cgroup-writes', action='store_true')
    parser.add_argument('--expected-host', default='bart')
    args = parser.parse_args()
    if not args.authorize_cgroup_writes:
        parser.error('Requires --authorize-cgroup-writes')
    if socket.gethostname() != args.expected_host:
        parser.error('Wrong host; refusing cgroup writes')
    root = Path('/sys/fs/cgroup') / ('tuxbot-smoke-' + uuid.uuid4().hex)
    root.mkdir()
    groups = Cgroups(root, ['A', 'B'])
    manager = None
    result = {}
    errors = []
    try:
        groups.create()
        controls = {a: cgroup_controls(path, {}) for a, path in groups.paths.items()}
        manager = Actuator(controls)
        before = manager.snapshot()
        manager.apply({'application_updates': {'A': {'cpu.weight': 200, 'cpu.max': '50000 100000'}, 'B': {'cpu.weight': 300}}})
        effective = manager.snapshot()
        assert effective['application_updates']['A']['cpu.weight'] == '200'
        assert effective['application_updates']['A']['cpu.max'] == '50000 100000'
        assert effective['application_updates']['B']['cpu.weight'] == '300'
        independent = Actuator({'A': controls['A']})
        for forbidden in ({'application_updates': {'B': {'cpu.weight': 1}}}, {'host_updates': {'napi_busy_poll': 1}}):
            try:
                independent.validate(forbidden)
            except ValueError:
                pass
            else:
                raise AssertionError('Scope escape allowed')
        probe = 'from pathlib import Path; import subprocess,sys; print(Path("/proc/self/cgroup").read_text().strip(),flush=True); subprocess.run([sys.executable,"-c",\'from pathlib import Path; print(Path("/proc/self/cgroup").read_text().strip())\'],check=True)'
        process = subprocess.run([sys.executable, '-m', 'extension.runner', '--child', str(groups.paths['A']), sys.executable, '-c', probe],
                                 capture_output=True, text=True, check=True, timeout=10)
        memberships = process.stdout.strip().splitlines()
        assert len(memberships) == 2 and all(root.name + '/A' in line for line in memberships), memberships
        errors.extend(manager.restore())
        assert manager.snapshot() == before
        _, report = resolve_host([])
        result.update(validated=True, cpu_controls=effective, inherited_memberships=memberships,
                      restored=True, host_compatibility=report)
    finally:
        for path in groups.created:
            if (path / 'cgroup.kill').is_file():
                (path / 'cgroup.kill').write_text('1')
        errors.extend(groups.await_empty())
        if manager:
            errors.extend(manager.restore())
        errors.extend(groups.cleanup())
        try:
            root.rmdir()
        except OSError as exc:
            errors.append(str(exc))
        result['cleanup_errors'] = errors
        print(json.dumps(result, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
