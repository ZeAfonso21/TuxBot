# TuxBot extension progress logs

The local checkout is the source of truth. Code/configuration changes are synchronized to `/work_dir/TuxBot` on **bart** before execution. All installations, tests, workloads, plots and system changes execute through `ssh bart 'COMMAND'`, never locally. Results may be copied back for inspection.

- [001 — First remote validation](001-remote-validation.md): original 16 tests, Gemini schema/model fixes and isolated cgroup smoke check.
- [002 — Real Sysbench A/C pilot](002-sysbench-pilot.md): workload selection, provisioning, failed setup attempt, 23 tests, concurrent default and coordinated runs, telemetry validation, costs/tokens, plots and limitations.

- [003 — Clarifications and next experiment plan](003-clarifications-and-experiment-plan.md): short-run versus 30/20 distinction, clearer plot colors, 24 tests and proposed workload-coupling study.

Current test summary: [`src/extension/TESTING.md`](../src/extension/TESTING.md).

## Retained pilot artifacts

Copied locally from bart, excluded from Git by the existing `results/` rule:

- [Per-window relative improvement](../results/pilot-01/comparison/improvement_per_window.png)
- [Common Configuration A reference](../results/pilot-01/comparison/improvement_vs_configuration_A.png)
- [Effective control trajectory](../results/pilot-01/comparison/control_trajectory.png)
- [Shared host telemetry](../results/pilot-01/comparison/host_telemetry.png)
- [Per-application resource telemetry](../results/pilot-01/comparison/application_resources.png)
- [Full result/plot directory](../results/pilot-01/)

These are the first real pilot data, not the temporary mocked-test graphs. Negative windows and the failed setup attempt are retained. A future checkout without the ignored result artifacts will need the remote results copied back separately.
