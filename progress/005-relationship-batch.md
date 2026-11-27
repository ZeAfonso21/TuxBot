# 005 — Completed real relationship batch

Full record, raw paths, screening effects, exact A/C medians and limitations: [results/relationships-01/README.md](../results/relationships-01/README.md).

All execution was on bart through SSH, with rsync synchronization. The successful batch ran in the **foreground** with tee logging and pipefail, completing in 59.50 minutes. The earlier background attempt failed before workload launch due to a missing output parent; its evidence is retained. No additional source implementation was done after the user requested execution only; the operational recipe lives with the results.

## Runs

Three real Sysbench pair/load regimes, qualified by two before/intervention/after screening cycles:

- Aligned: two four-thread CPU prime workloads; a shared frequency-cap reduction hurt both throughputs by about 9.8%.
- Conflicting: eight-thread CPU latency plus eight-thread memory-read throughput; increasing CPU cgroup weight improved latency 60–65% while reducing memory throughput 59–61%.
- Weakly related: one CPU thread on CPU 0 and one memory thread on CPU 2; a CPU-only half-core quota increased CPU latency from 2.66 to 52.89 ms while changing memory throughput only +0.54%.

These are **control/load-specific relationships**, not three different benchmark suites or intrinsic classifications. First conflicting-screen reference CPU drift reached −8.60%; retain that uncertainty rather than claim significance.

Each pair then completed one A and one C run, each with 3 baseline + 30 comparison/tuning + 20 stable eight-second windows. A is now actually no-dedicated-cgroup: launcher membership equals inherited membership, with no cgroup accounting substituted for process data. C uses scoped cgroups and the existing host/dual-loop controls. All reports pass strict no-cgroup-A provenance validation without legacy waivers.

Stable C improvements versus A (positive better):

| Pair | First metric | Second metric |
|---|---:|---:|
| CPU/CPU aligned | −0.098866% throughput | −0.026793% throughput |
| CPU/memory conflicting | −5.589768% latency reduction | −0.316018% memory throughput |
| CPU/memory weak | −1.879699% latency reduction | −0.536120% memory throughput |

**No stable aggregate gain was observed.** One sequential A→C run pair per case is not a statistical test; small differences may be drift/noise. All negative outcomes and per-window fluctuations are retained.

## Verification and provenance

- 48 extension tests passed before live execution.
- All six full runs completed; all 318 measured windows have positive shared IPC, cycles, instructions and RAPL data.
- Recorded controls are constant within every measured window; each stable phase has a single frozen configuration.
- All run/pilot restoration errors are empty. Original six host values and `memory pids` delegation were restored; no experiment groups or workload processes remained.
- Four main figure pairs, optional scoped telemetry, native logs, timestamped intervals, input JSON, raw results, inference records and final audit are stored locally and remotely under `results/relationships-01/`.
- 183 recorded inference decisions; 10,205,276 reported billable tokens. Monetary spend is not independently verified; see `validation/inference-usage.json`.
- An unnecessary TailBench clone attempt was removed and its 2.9 GiB recovered. It is not a dependency or data source for these runs.

Remaining: independent repetitions/randomized order, actual B experiments, other benchmark suites and statistical conclusions. Older analysis/testing sections describe earlier stages; this measured batch supersedes their statement that no no-cgroup A data exists.
