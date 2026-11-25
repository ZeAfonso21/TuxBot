"""Workload bridge reusing existing TailBench startup and interval aggregation.

Only timestamped interval CSVs are accepted: no mtime/log fallback or overlapping end slack.
This module never constructs an optimizer or modifies host controls.
"""
import argparse
import json
import os
from pathlib import Path

from .controls import decode
from .model import positive


def bridge(action, filename):
    from optimizer.config import SimpleConfig
    from optimizer.benchmarks.tailbench import TailbenchBenchmark
    data = decode(Path(filename).read_text())
    config = SimpleConfig(**data)
    benchmark = TailbenchBenchmark(config)
    if action == 'serve':
        if not benchmark.output_dir:
            raise ValueError('A unique tailbench_output_dir is mandatory for each workload/run')
        try:
            if not benchmark.pre_execute():
                raise RuntimeError('TailBench startup failed')
            ready = os.environ.get('TUXBOT_READY_FILE')
            if ready:
                Path(ready).write_text('ready\n')
            status = benchmark.benchmark_process.wait()
            raise RuntimeError(f'TailBench unexpectedly exited: {status}')
        finally:
            benchmark.cleanup()
    else:
        start = float(os.environ['TUXBOT_WINDOW_START'])
        end = float(os.environ['TUXBOT_WINDOW_END'])
        intervals = []
        for file in sorted(Path(benchmark.metrics_dir).glob('lats_interval_*.csv')):
            record = benchmark._read_interval_metrics_file(str(file))
            if not record or 'parsed_timestamp' not in record:
                continue
            timestamp = record.pop('parsed_timestamp').timestamp()
            if start <= timestamp < end:
                for name in ('count', 'sojourn_mean_ms', 'sojourn_p50_ms', 'sojourn_p95_ms', 'sojourn_p99_ms', 'sojourn_max_ms'):
                    positive(record.get(name))
                intervals.append(record)
        if not intervals:
            raise ValueError('No timestamped TailBench intervals in the exact common window')
        aggregate = benchmark._aggregate_metrics(intervals)
        result = dict(window_start=start, window_end=end, latency_p99=aggregate['sojourn_p99_ms'],
                      throughput=aggregate['throughput'], intervals=len(intervals),
                      percentile_semantics='maximum of interval p99s, not pooled request p99')
        print(json.dumps(result, allow_nan=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['serve', 'measure'])
    parser.add_argument('config')
    args = parser.parse_args()
    bridge(args.action, args.config)


if __name__ == '__main__':
    main()
