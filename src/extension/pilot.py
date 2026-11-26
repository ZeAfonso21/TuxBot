"""Explicitly gated remote pilot wrapper: temporary CPU delegation + original runner.

No benchmark logic or tuning policy lives here. The wrapper verifies expected
initial host values, provisions an exclusive empty root, and restores delegation.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import signal
import subprocess
import sys
import time
from .controls import decode
from .host import resolve_host
from .runner import save


def execute(filename, expected_host):
    if socket.gethostname() != expected_host:
        raise RuntimeError('Wrong hostname; refusing experiment setup')
    data = decode(Path(filename).read_text())
    output = Path(data['results_dir']).resolve()
    if output.exists():
        raise ValueError('Run output already exists; use a new run identifier')
    host, _ = resolve_host(data.get('approved_host_parameters', []))
    expected = data['expected_initial_host']
    if set(expected) != set(host):
        raise ValueError('Every approved active host control must have an expected initial value')
    initial_host = {k: c.read() for k, c in host.items()}
    if initial_host != {k: str(v) for k, v in expected.items()}:
        raise ValueError(f'Host is not in the expected initial state: {initial_host}')
    root = Path(data['cgroup_root'])
    if root.parent != Path('/sys/fs/cgroup') or root.exists():
        raise ValueError('Pilot requires a fresh direct child of /sys/fs/cgroup')
    parent = Path('/sys/fs/cgroup/cgroup.subtree_control')
    before = parent.read_text().split()
    report = dict(hostname=expected_host, initial_host=initial_host, parent_controllers_before=before,
                  started=time.time(), errors=[])
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence = output.with_suffix('.delegation.json')
    save(evidence, report)
    created = False
    try:
        if 'cpu' not in before:
            parent.write_text('+cpu')
        root.mkdir()
        created = True
        for name, value in (('cpu.max', 'max 100000'), ('cpu.weight', '100'), ('memory.high', 'max'), ('memory.max', 'max')):
            if (root / name).read_text().strip() != value:
                raise ValueError(f'New experiment parent has non-default {name}')
        if data.get('defaults_verified') is not True:
            raise ValueError('Review initial-state requirements before setting defaults_verified')
        env = dict(os.environ, OS_PARAM_TUNING_ROOT=str(Path(__file__).resolve().parents[2]), LC_ALL='C')
        argv = [sys.executable, '-m', 'extension.runner', str(Path(filename).resolve()), '--authorize-execution']
        with subprocess.Popen(argv, env=env) as child:
            try:
                status = child.wait()
            except BaseException:
                child.terminate()
                child.wait()  # never restore host state while its tuner can still write
                raise
            if status:
                raise subprocess.CalledProcessError(status, argv)
    finally:
        if created:
            try:
                root.rmdir()
            except OSError as exc:
                report['errors'].append(f'Experiment root removal: {exc}')
        try:
            if 'cpu' not in before and 'cpu' in parent.read_text().split():
                parent.write_text('-cpu')
            report['parent_controllers_after'] = parent.read_text().split()
            if set(report['parent_controllers_after']) != set(before):
                report['errors'].append('Parent controller state differs after restoration')
        except OSError as exc:
            report['errors'].append(f'Parent restoration: {exc}')
        try:
            report['host_after'] = {k: c.read() for k, c in host.items()}
            if report['host_after'] != initial_host:
                report['errors'].append('Host tunables differ after restoration')
        except OSError as exc:
            report['errors'].append(f'Host readback: {exc}')
        report['finished'] = time.time()
        save(evidence, report)
        if report['errors']:
            raise RuntimeError(f'Pilot restoration incomplete; see {evidence}: {report["errors"]}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config')
    parser.add_argument('--authorize-execution', action='store_true')
    parser.add_argument('--expected-host', default='bart')
    args = parser.parse_args()
    if not args.authorize_execution:
        parser.error('Explicit --authorize-execution is required for real experiments')
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f'signal {signum}')
    signal.signal(signal.SIGTERM, interrupted)
    execute(args.config, args.expected_host)


if __name__ == '__main__':
    main()
