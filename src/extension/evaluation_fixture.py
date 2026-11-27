"""Explicitly synthetic rendering fixtures. No benchmark/system/provider code is used."""
import argparse
import copy
import json
from pathlib import Path


def fixture_runs():
    apps = [dict(id='cpu_latency', metric='latency_p99_ms', objective='minimize', baseline=8, bound='default'),
            dict(id='memory_bandwidth', metric='throughput_mib_s', objective='maximize', baseline=50, bound='default')]
    conditions = {'cpu_latency': {'program': 'SYNTHETIC CPU'}, 'memory_bandwidth': {'program': 'SYNTHETIC memory'}}
    runs = []
    for mode in ('default', 'coordinated'):
        data = dict(data_kind='synthetic', mode=mode, completed=True, applications=copy.deepcopy(apps),
                    provenance={'dedicated_workload_cgroups': mode == 'coordinated', 'concurrent_workloads': True},
                    config=dict(tuning_windows=2, stable_windows=3, window_seconds=1, warmup_seconds=0,
                                workload_conditions=conditions), windows=[])
        initial = dict(application_updates={a['id']: {'cpu.weight': '100', 'cpu.max': 'max 100000'} for a in apps},
                       host_updates={'latency_ns': '24000000', 'min_perf_pct': '45', 'custom_knob': '5'})
        initial['application_updates']['memory_bandwidth']['memory.high'] = 'max'
        if mode == 'coordinated':
            data['config']['cgroup_root'] = '/sys/fs/cgroup/SYNTHETIC-NOT-CREATED'
            data['initial_configuration'] = copy.deepcopy(initial)
        for position, number in enumerate((-1, -2, -3, 1, 2, 3, 4, 5)):
            phase = 'baseline' if number < 0 else 'tuning' if number < 3 else 'stable'
            values = [8, 50] if number < 0 else [4, 100] if mode == 'default' else [[5, 110], [3, 90], [5, 80], [3.2, 120], [3, 118]][number - 1]
            row = dict(window=number, phase=phase, start=position, end=position + 1, applications={},
                       shared={'cpu_load_socket0_pct': 50, 'instructions_per_cycle': 1.2, 'power_socket0_watts': 45})
            for app, value in zip(apps, values):
                row['applications'][app['id']] = dict(metric=app['metric'], objective=app['objective'], current=value,
                                                       raw={'window_start': position, 'window_end': position + 1},
                                                       bound=app['baseline'])
            if mode == 'coordinated':
                snapshot = copy.deepcopy(initial)
                if number > 1:
                    snapshot['application_updates']['cpu_latency'].update({'cpu.weight': '400', 'cpu.max': '400000 100000'})
                    snapshot['application_updates']['memory_bandwidth']['memory.high'] = '2147483648'
                    snapshot['host_updates'].update({'latency_ns': '12000000', 'min_perf_pct': '80', 'custom_knob': '7'})
                row.update(configuration_start=snapshot, configuration_end=copy.deepcopy(snapshot),
                           observed_host_start=copy.deepcopy(snapshot['host_updates']))
                for app in apps:
                    row['applications'][app['id']].update(
                        cgroup_window={'cpu_usage_cores': 1.5, 'memory_current_bytes': 536870912},
                        resource_scope={'kind': 'cgroup', 'path': data['config']['cgroup_root'] + '/' + app['id']})
            data['windows'].append(row)
        runs.append(data)
    return tuple(runs)


def write_fixtures(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for name, data in zip(('A-synthetic.json', 'C-synthetic.json'), fixture_runs()):
        (output / name).write_text(json.dumps(data, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    write_fixtures(args.output)


if __name__ == '__main__':
    main()
