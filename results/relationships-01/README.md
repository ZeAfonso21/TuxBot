# Completed relationship batch — bart

Executed **in the foreground via SSH**, 27 November 2026, in 59.50 minutes. All artifacts were copied from `/work_dir/TuxBot/results/relationships-01/` with rsync. This batch uses three **Sysbench pair/load/affinity regimes**, not three different benchmark suites. No TailBench data or dependencies were needed for these runs.

## Measured relationship screens

Relationships are specific to the listed control and fixed load, not intrinsic benchmark labels. Each screen ran two before/intervention/after cycles, three 8-second windows per phase, 3 seconds of settling per phase and a 10-second initial warmup. Reference = median of six before/after window metrics for that cycle; intervention = median of its three windows. Controls reset to their captured initial values between phases. Thresholds were declared in the execution recipe before measurement: aligned/conflicting responses each at least 5%, same/opposite signs; weak response at least 10% for CPU with memory within 3%.

| Relationship | Actual pair | Intervention | Cycle 1 response | Cycle 2 response |
|---|---|---|---|---|
| Aligned | Sysbench CPU prime limits 10000 / 20000; four threads each | Shared `max_perf_pct` 100 → 80 | Throughputs −9.780% / −9.892% | −9.850% / −9.844% |
| Conflicting | CPU p99 latency / sequential memory-read throughput; eight threads each | CPU workload `cpu.weight` 100 → 1000; memory weight remains 100 | CPU latency reduction +60.471%; memory throughput −59.223% | +65.135%; −60.752% |
| Weakly related | One CPU thread pinned to CPU 0 / one memory thread pinned to CPU 2 (different physical cores) | CPU workload quota unlimited → `50000 100000` (half a core) | CPU latency reduction −1888.346%; memory throughput +0.538% | −1888.346%; +0.538% |

The aligned intervention worsened both apps; restoring the cap improves both relative to the restricted state. The untuned full experiment already starts at 100%, so this does **not** imply headroom above default.

The weak relationship is demonstrated for the local quota under that affinity/load, not for every host control; LLC, memory and P-state resources remain shared. CPU latency increased from 2.66 to 52.89 ms during quota restriction. Conflicting-screen CPU reference drift reached −8.60% in one cycle; the much larger intervention response repeated in both cycles, but these remain descriptive screens, not significance tests.

Raw screens: each case's `screen/results.json`, native `.sysbench.log` files, timestamped interval JSONL, telemetry and `progress.json`. Exact intervention/reference values and measured drift: `batch-status.json`.

## Full A/C experiments

All six runs completed. Each has **3 concurrent baseline + 30 comparison/tuning + 20 stable windows**, 8 seconds/window, following workload readiness and 10 seconds warmup. A's 30 comparison windows are untuned; C uses the existing Actor–Speculator loop and freezes parameters before its 20 stable windows.

- **A:** no dedicated workload cgroups, no tuner or kernel-control writes. Captured launcher membership matches inherited membership; no ancestor accounting was substituted for per-app data.
- **C:** separate per-workload cgroups plus the six previously verified host controls, with transactional validation/readback and restoration. Same workload settings and affinity as A.
- CPU p99 metric = maximum of contained one-second interval p99 reports within each window, **not pooled request p99**. CPU EPS / memory throughput average the contained reports.
- Each memory thread uses its own 256 MiB local, sequential-read buffer. Eight threads therefore use 2 GiB of buffers, versus 256 MiB in the partitioned case.

### Stable-phase results (raw medians first, then ordinary signed percentages)

Positive means better; negative means worse. Reference = that case's A stable-window median, fixed for all C windows. No A/C window-index pairing.

| Case | Metric | A median | C median | C improvement |
|---|---|---:|---:|---:|
| Aligned CPU/CPU | Prime 10000 events/s | 2816.213571 | 2813.429286 | **−0.098866%** |
| Aligned CPU/CPU | Prime 20000 events/s | 1095.722143 | 1095.428571 | **−0.026793%** |
| Conflicting CPU/memory | CPU latency ms | 21.110 | 22.290 | **−5.589768%** |
| Conflicting CPU/memory | Memory MiB/s | 21243.393571 | 21176.260714 | **−0.316018%** |
| Weak CPU/memory | CPU latency ms | 2.660 | 2.710 | **−1.879699%** |
| Weak CPU/memory | Memory MiB/s | 13641.142857 | 13568.010000 | **−0.536120%** |

**No stable aggregate improvement was observed in these runs.** Each case is one sequential A→C pair, without randomized order, independent repetitions or confidence intervals. Small differences may be run drift/noise; they are not established causal regressions. The relationship screens and tuning outcomes are distinct results. The tuner uses its own concurrent initial C measurements for its internal default bounds; the external report always uses A's steady reference.

## Reports

Each comparison directory includes the four main PNG/PDF figures, optional scoped telemetry, CSVs, source hashes, reference/window metadata and quality notes:

- [Aligned CPU/CPU](cpu-cpu-frequency/comparison/evaluation.md)
- [Conflicting CPU/memory](cpu-memory-contention/comparison/evaluation.md)
- [Weak CPU/memory](cpu-memory-partitioned/comparison/evaluation.md)

Use native JSON/CSVs for exact values. The generic relative-improvement figure footer mentions the CPU p99 aggregation caveat even for the CPU/CPU EPS case; that caveat does **not** apply to its EPS metrics, whose panels, raw records and CSVs correctly use events/s.

## Checks, logs and usage

- `validation/final-audit.json`: all six runs completed with exactly 3/30/20 windows; constant within-window controls; one frozen stable configuration per run; positive host IPC/instructions/cycles/RAPL in **all 318 full-run windows**.
- Every run's `.delegation.json` and `results.json` reports no restoration error. Six approved host values returned to their captured defaults; root delegation returned to `memory pids`. No workload process or `tuxbot-rel01-*` cgroup remained.
- `validation/pytest.log`: 48 extension tests passed before execution.
- `batch.log`: foreground output with propagated failure status; `run_batch.py`: batch execution recipe, not a new optimizer. `configs/`: exact run/workload inputs.
- `validation/inference-usage.json`: 183 recorded decisions (90 Speculator, 93 Actor, including final refreshes), no recorded decision errors; 9,957,102 input + 55,882 output + 192,292 thinking tokens; 10,205,276 reported total/billable tokens. **Monetary spend was not independently verified.** No further API requests were made for reporting.

## Retained initial setup failure

The initial background attempt failed creating a missing results parent directory, before workload launch or system changes. Its log/status are preserved as `batch-attempt-01*`. Only the batch recipe's directory creation was corrected; the successful batch then ran entirely in the foreground. No runs were overwritten or hidden. An earlier unnecessary TailBench checkout attempt was removed, recovering its space; no cloned source is used in this batch.
