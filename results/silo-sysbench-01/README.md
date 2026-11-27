# Silo p99 latency vs Sysbench CPU throughput

## Completed experiment: run-02

[Report](run-02/comparison/evaluation.md) · [Final audit](run-02/final-audit.json) · [Foreground log](run-02/experiment.log)

Executed on bart via SSH in the foreground. Source/configuration and results are synchronized with rsync. No affinity partitioning was used. Both workloads ran concurrently across the available CPUs.

- **Silo:** pinned TailBench revision `2f3098b539a9a3413086fc77e29637937bafd116`, TPC-C, scale factor 4, four worker threads, **1000 offered requests/s**.
- **Sysbench CPU:** version 1.0.20, eight threads, prime limit **50000**, seed 1; maximize CPU events/s.
- Both phases: application readiness, **20 seconds warmup**, three baseline windows, **30 comparison/tuning + 20 stable windows**, eight seconds/window.
- **A:** no dedicated workload cgroups or kernel-control writes. Captured existing OS settings, not TuxBot-initialized knob defaults. A's 30 comparison windows remain untuned.
- **C:** per-workload CPU weights/quotas plus the six previously verified scheduler/P-state controls; existing Actor–Speculator loop, Flash Actor / Flash-Lite Speculator, updates outside measured windows, final Actor refresh before frozen stable measurements.

## One common reference, established before tuning

Reference = **arithmetic mean of A's first three concurrent window metrics**, used unchanged by both the C tuner and report. The full A source hash, selected windows, workload conditions and reference values are recorded in C's `baseline_reference`; mismatched references are rejected.

| Metric | A initial window 1 | A initial window 2 | A initial window 3 | Fixed mean |
|---|---:|---:|---:|---:|
| Silo p99 summary (ms) | 0.404 | 0.400 | 0.364 | **0.3893333333** |
| Sysbench CPU events/s | 611.715714 | 611.285714 | 611.285714 | **611.4290476190** |

C's own initial measurements remain in the raw results as diagnostics; they do not replace this reference. `measured_initial_baselines` distinguishes them from the shared targets. The controller's iteration-0 compatibility entry is a reference-only seed, not an additional measured window; actual C initial windows and subsequent tuning observations are stored separately.

For the stable summary, aggregate the **20 raw C stable windows by arithmetic mean**, then calculate latency reduction `100*(A-C)/A` and throughput increase `100*(C-A)/A`. No best-so-far curves, per-window percentage averaging, or index-pairing with unrelated A windows.

## Results

| Metric | Fixed A reference | C stable mean | Improvement |
|---|---:|---:|---:|
| Silo latency summary | 0.389333 ms | 0.504150 ms | **−29.490582%** |
| Sysbench throughput | 611.429048 events/s | 611.342429 events/s | **−0.014167%** |

**No stable Pareto improvement was observed.** Silo exceeded the shared reference bound in 15/20 stable windows; Sysbench fell below its bound in 9/20. Execution completion does not imply optimization/constraint success. The existing policy still records performance violations rather than automatically falling back to a verified best configuration.

A's later untuned stable mean was **0.456350 ms / 611.625786 events/s**. Thus A itself exhibited roughly 17.21% latency drift relative to its first-three reference. These later values do not replace the requested reference, but are important context: C latency is approximately 10.47% higher than A's later stable mean. One sequential A→C pair and a three-window reference do **not** establish causal or statistically significant regression.

The pair was selected as a candidate conflicting relationship. These runs do not independently prove that classification at 1000 offered requests/s; no controlled single-knob causal sweep or independent repetitions were performed. The observed stable result is neither a demonstrated Pareto improvement nor proof of a globally optimal trade-off.

### Figures

- [Per-window improvement](run-02/comparison/relative_improvement.png)
- [Stable summary](run-02/comparison/stable_performance.png)
- [Actual applied controls](run-02/comparison/applied_parameters.png)
- [Joint/Pareto observations](run-02/comparison/pareto_tradeoffs.png)
- [Optional scoped resource diagnostics](run-02/comparison/resource_telemetry.png)

PDF counterparts, CSVs, source hashes and quality notes are in the same directory. There is no invented A per-app cgroup/process telemetry.

## Metric semantics

Silo's window summary is the **maximum of interval sojourn-p99 summaries selected by their CSV timestamps**, not a pooled request percentile. Native CSV timestamps have one-second resolution; they do not provide exact per-request boundary attribution. Sysbench EPS averages completed one-second interval reports wholly contained in each common window. Perf measures the central six seconds of the eight-second window, while system telemetry uses the existing collector schedule. These conventions are preserved, not silently presented as full-window request-level statistics.

## Initial overloaded attempt retained

The initial candidate at **10000 Silo requests/s** is retained under root `A/`, `workloads/A/`, `configs/`, `experiment.log` and `run_experiment-attempt-01.py`. It completed the untuned A measurements, but latency grew: its initial mean was 1458.514333 ms and its late mean exceeded twice that reference. The predeclared stationarity guard therefore stopped **before any C/API tuning**. That attempt is not mixed into run-02, and was not overwritten.

`run_experiment.py` records the successful operational recipe, defaulting to run-02 and 1000 requests/s. Installed binary/build/smoke evidence is under [install/](install/README.md). The runtime uses isolated native working directories because the pinned harness writes CSVs to cwd.

## Validation, cleanup and usage

- **52 extension tests passed** on bart; logs/JUnit under `validation/`. Tests cover mean vs median, matching shared references, invalid provenance/conditions, and SIGTERM-triggered native cleanup, as well as the prior extension suite.
- Both successful runs have exactly **3/30/20** windows, constant recorded controls within each window and a single frozen configuration throughout each stable phase.
- All **106** successful full-run windows have positive host instructions, cycles, IPC and RAPL power metrics.
- All restoration errors and pilot wrapper errors are empty. Host settings equal the captured A initial state; parent delegation returned to `memory pids`. No native Silo, Sysbench or experiment cgroup remained. Native Silo's separate process session is now gracefully cleaned before A exits and before C launches.
- C recorded **61 decisions**: 30 Speculator and 31 Actor, including final refresh. Reported totals: **3,297,881 input + 18,635 output + 59,951 thinking = 3,376,467 billable tokens**. Monetary spend is not independently verified. No model calls were made for reporting or the overloaded A attempt.

## Minimal execution changes

The original dual-loop search policy remains unchanged. Extension-only changes add opt-in mean aggregation and a validated shared A reference, graceful bridge/native cleanup, and matching report normalization/labels. Historical runs without a shared reference retain their previous median policy and were not rewritten.
