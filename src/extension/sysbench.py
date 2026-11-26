"""Continuous Sysbench CPU/memory bridge with timestamped one-second app reports.

The legacy Sysbench adapter restarts each window and parses a final summary. This
bridge keeps both applications alive across baseline/tuning/stable phases. OS
telemetry still comes from the existing TuxBot collectors, not this bridge.
"""
import argparse
import json
import os
from pathlib import Path
import re
from statistics import mean
import subprocess
import time

from .controls import decode
from .model import positive

CPU = re.compile(r'^\[\s*([\d.]+)s\s*\].*eps:\s*([\d.]+)\s+lat \(ms,99%\):\s*([\d.]+)')
MEMORY = re.compile(r'^\[\s*([\d.]+)s\s*\]\s*([\d.]+) MiB/sec')


def parse_interval(line, workload):
    match = (CPU if workload == 'cpu' else MEMORY).search(line)
    if not match:
        return None
    values = [positive(float(value)) for value in match.groups()]
    if workload == 'cpu':
        return dict(elapsed=values[0], events_per_second=values[1], latency_p99_ms=values[2])
    return dict(elapsed=values[0], throughput_mib_s=values[1])


def command(config):
    workload = config['workload']
    threads = config.get('threads', 4)
    if workload not in ('cpu', 'memory') or type(threads) is not int or not 1 <= threads <= 64:
        raise ValueError('Use cpu/memory and 1..64 threads')
    argv = ['stdbuf', '-oL', 'sysbench', workload, f'--threads={threads}', '--time=0',
            '--events=0', '--report-interval=1', '--percentile=99', '--rand-seed=1']
    if workload == 'cpu':
        argv.append(f"--cpu-max-prime={config.get('cpu_max_prime', 20000)}")
    else:
        # Four private 256 MiB buffers exceed bart's 8 MiB LLC without OOM limits.
        argv += ['--memory-block-size=256M', '--memory-total-size=1000000G',
                 '--memory-scope=local', '--memory-oper=read', '--memory-access-mode=seq']
    return argv + ['run']


def serve(config):
    path = Path(config['metrics_file'])
    path.parent.mkdir(parents=True, exist_ok=True)
    argv = command(config)
    previous_elapsed = 0
    with path.open('x') as metrics, path.with_suffix('.sysbench.log').open('x') as log:
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, bufsize=1, env=dict(os.environ, LC_ALL='C'))
        try:
            for line in process.stdout:
                end = time.time()
                log.write(line)
                log.flush()
                record = parse_interval(line, config['workload'])
                if record is None:
                    continue
                interval = record['elapsed'] - previous_elapsed
                if interval <= 0:
                    raise ValueError('Sysbench elapsed time did not increase')
                previous_elapsed = record['elapsed']
                record.update(start=end - interval, end=end,
                              clock='wall-clock receipt time; interval length from sysbench elapsed time')
                metrics.write(json.dumps(record, allow_nan=False) + '\n')
                metrics.flush()
                ready = os.environ.get('TUXBOT_READY_FILE')
                if ready and not Path(ready).exists():
                    Path(ready).write_text('ready\n')
            raise RuntimeError(f'Sysbench exited unexpectedly: {process.wait()}')
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def measure(config, start, end):
    records = []
    for line in Path(config['metrics_file']).read_text().splitlines(keepends=True):
        # A concurrently-written final line is not an observation until newline-terminated.
        if not line.endswith('\n'):
            continue
        record = decode(line)
        if start <= record['start'] and record['end'] <= end:
            records.append(record)
    if len(records) < max(1, int((end - start) * 0.6)):
        raise ValueError(f'Too few complete Sysbench intervals in common window: {len(records)}')
    result = dict(window_start=start, window_end=end, intervals=len(records),
                  interval_coverage_seconds=sum(r['end'] - r['start'] for r in records),
                  metric_time_semantics='complete one-second reports contained in the common window; receipt timestamps')
    if config['workload'] == 'cpu':
        result.update(latency_p99_ms=max(positive(r['latency_p99_ms']) for r in records),
                      events_per_second=mean(positive(r['events_per_second']) for r in records),
                      percentile_semantics='maximum of interval p99 latency, NOT pooled request p99')
    else:
        result['throughput_mib_s'] = mean(positive(r['throughput_mib_s']) for r in records)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['serve', 'measure'])
    parser.add_argument('config')
    args = parser.parse_args()
    config = decode(Path(args.config).read_text())
    if args.action == 'serve':
        serve(config)
    else:
        result = measure(config, float(os.environ['TUXBOT_WINDOW_START']), float(os.environ['TUXBOT_WINDOW_END']))
        print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
