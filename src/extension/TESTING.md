# TuxBot extension — current testing status

**Local checkout = source of truth. All execution takes place on bart via SSH.** Source changes are synchronized to `/work_dir/TuxBot`; no TuxBot, benchmark, test, dependency installation or system tuning is executed locally.

## Progress history

- [001 — Initial remote validation](../../progress/001-remote-validation.md): 16 tests, schema/model compatibility fixes, two bounded Gemini no-op checks and isolated real-cgroup validation.
- [002 — Real Sysbench A/C pilot](../../progress/002-sysbench-pilot.md): workload provisioning, failed setup and fix, 23 tests, actual co-located A and coordinated C sessions, telemetry, plots, restoration, token usage and limitations.
- [003 — Run lengths, plot colors and next experiment plan](../../progress/003-clarifications-and-experiment-plan.md).
- [Progress/artifact index](../../progress/README.md).

The logs preserve what was known at each stage; an earlier "untested" statement describes that stage, not the current status below.

## Latest verified status

- Remote: **bart**, Linux `5.15.0-89-lowlatency`, Python 3.10.12.
- Isolated Python environment: `/work_dir/tuxbot-venv`.
- Native benchmark: **Sysbench 1.0.20**, installed on bart. CPU and memory workloads require no database/dataset. TailBench remains unprovisioned and is not used for this pilot.
- Perf installed by the user; hardware counters verified with actual co-located workloads.
- **24 targeted tests pass**: unit validation, original perf-parser tests, mocked controller/runner lifecycle and privacy, failure handling, real collector construction, continuous Sysbench parsing, cgroup rates, narrowed host ranges, hostname gate, CSV and plot generation. Latest evidence: local/remote `results/pilot-01/validation/`.
- **A and C completed**, each with three concurrent baseline windows, eight default/tuning windows and three stable windows, all 8 seconds long. Both workloads stayed alive together throughout each run.
- **17 validated C decisions** (8 Speculator + 9 Actor including final freeze) applied real cgroup and host changes with zero recorded actuation errors. Models: Gemini 3.5 Flash / Flash-Lite.
- All 14 windows in each run contain shared cycles/instructions/IPC/cache misses, CPU load and RAPL power, plus app metrics and cgroup resource/pressure observations.
- Exact selected host/app snapshots and ancestor CPU-delegation state restored after each run. No experimental cgroups/workloads remained in the post-run check.
- First A setup failure retained: an abstract `cleanup` omission prevented collector construction before workload startup. Fixed and regression-tested; successful retry is `A-default-02`, not an overwritten failure.

## Retained real plots and data

Copied into the local source checkout for inspection, also retained on bart:

**`results/pilot-01/comparison/`**

- [Per-window improvement](../../results/pilot-01/comparison/improvement_per_window.png)
- [Shared Configuration A reference](../../results/pilot-01/comparison/improvement_vs_configuration_A.png)
- [Control trajectory](../../results/pilot-01/comparison/control_trajectory.png)
- [Host telemetry](../../results/pilot-01/comparison/host_telemetry.png)
- [Application resources](../../results/pilot-01/comparison/application_resources.png)
- Raw CPU/memory performance comparisons, PNG/PDF versions, CSV tables and `pilot-summary.json`.

Plotting source: [`report.py`](report.py) and [`plots.py`](plots.py). The earlier mock-test plots were temporary and did not survive test cleanup; these are now retained real measurements.

Initial stable medians: CPU max-interval-p99 **3.89 ms (A) → 3.36 ms (C)**; memory throughput **21577.16 → 21760.09 MiB/s**. This is one short pilot, **not a statistically established research gain**. CPU metric is a maximum of interval p99s, never a pooled request p99. Relative-improvement curves use ratio factors, not latency-reduction percentages. See log 002 for baseline drift, raw violating windows and interpretation.

## Commands / credentials

Execute only remotely, for example:

```sh
ssh bart 'cd /work_dir/TuxBot && OS_PARAM_TUNING_ROOT=/work_dir/TuxBot MPLBACKEND=Agg PYTHONPATH=src /work_dir/tuxbot-venv/bin/python -m pytest -q src/extension/test_extension.py src/extension/test_controller.py src/extension/test_runner.py src/extension/test_sysbench.py tests/test_perf_collection.py'
```

`OS_PARAM_TUNING_ROOT` avoids copied-repository ownership/Git root-discovery issues without globally trusting unrelated repositories. The key remains outside the repository in `/work_dir/.secrets/gemini.env` (0600; directory 0700). Load it into remote tuning processes with `. /work_dir/.secrets/gemini.env`; do not display its contents or put it into JSON. A scan found no key bytes in copied pilot artifacts. SSH keys/passphrases were not accessed.

C reported **463170 billable tokens** across recorded successful decisions (445546 input, 4876 output, 12748 thinking). The user subsequently reported approximately €0.30 spent and confirmed the €10 budget may be used. No charge/account balance was independently verified through a billing API. No attempt was made to spend down the budget.

## Not yet established

- Full 30-tuning/20-stable-window runs: the completed A/C sessions used only 8/3 plus three baseline windows.
- Independent-mode B with real workloads; repeated/rerandomized A/C experiments or uncertainty estimates.
- General performance superiority, or causal isolation of individual controls/contextual awareness.
- Real full-session interruption/partial-kernel-write failure recovery, memory.high under load and other workload adapters.
- Exact request-level percentile reconstruction: the current pilot intentionally uses interval summaries and receipt-time alignment.
- Full privileged legacy test suite (intentionally not run).

Do not rerun the current pilot profiles into existing result/metrics paths. Create new run IDs and review the expected-default checks first. Raw artifacts stay under the existing ignored `results/` directory; code/config/progress logs remain separate from experiment data.
