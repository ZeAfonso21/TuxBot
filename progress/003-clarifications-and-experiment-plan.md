# 003 — Run-length clarification, plot colors and next experiment plan

## Clarification: the first run was short

The first real A/C pair used three baseline windows, **eight** tuning/default windows and **three** stable windows, each eight seconds long. It did **not** use the paper-style **30 tuning + 20 stable windows**. "Completed" meant the configured short validation session finished and restored its state, not that the full evaluation budget had been run.

`pilot.py` was named for this preliminary validation. It is a safety/setup supervisor (hostname/default verification, temporary delegation and restoration), not another optimizer. Window counts are configuration-driven, so the same controller can run 30/20 without changing the tuning algorithm. `runner.py` remains the actual application/measurement/tuning lifecycle.

`sysbench.py` adapts native one-second Sysbench reports to common TuxBot windows. Original Sysbench code is not modified. Unlike the original TuxBot adapter, it starts each app once per experiment, rather than starting another Sysbench process each window. Both apps remain alive during warmup, baseline, tuning and stable phases. The existing TuxBot collectors still gather host perf/power/load telemetry. This consistent A/C lifecycle is an extension protocol, not an exact reproduction of the original paper's per-window Sysbench process lifecycle.

## Plot change performed

The inspected common-A-reference PNG was teal for C and gray for A, not entirely grayscale. To make modes unambiguous, changed the shared plotting palette and styles:

- A/default: blue, dashed, circles.
- B/independent: green, dash-dot, diamonds.
- C/coordinated: orange, solid, squares.

Added a plot-mode distinguishability regression test. **24 tests pass** remotely. Regenerated the existing JSON results on bart and copied refreshed PNG/PDF/CSV/test artifacts into local `results/pilot-01/`. No new workload/tuning session, kernel change or LLM call occurred in this update. Numerical observations are unchanged.

## Budget feedback

The user reports the previous work cost approximately **€0.30** and permits use of the original €10 credit budget. This is user-reported cost, not a billing API/account-balance measurement. Token totals remain in log 002 and raw histories.

## Proposed next study — not executed yet

Introduce real TailBench applications and use **3 concurrent baseline + 30 tuning + 20 stable windows** for evaluation runs, with identical workload/measurement conditions in A/B/C. A runs the same window counts without a tuner; B should eventually use the same workload pair in two private controllers. Repeat and vary run order before claiming robust gains.

Study three kinds of **parameter-response coupling**:

1. **Aligned:** a shared-control change benefits both applications.
2. **Conflicting:** the same change improves one and worsens the other, e.g. redistributing a scarce CPU budget.
3. **Weakly coupled:** a control mainly affects one application while the other's metric changes little.

These labels are not intrinsic to a benchmark name, nor equivalent to minimizing latency versus maximizing throughput. The same application pair may be aligned for one host control and conflicting for a cgroup allocation. Determine labels from measurements under explicit load levels; do not cherry-pick pairs after seeing only favorable coordinated outcomes or assume all unlike resource demands are independent.

An initial real-application candidate is **TailBench Silo + img-dnn**, already represented by the extension bridge/examples, followed by a resource-competing pair after checking build/data/storage requirements. Pair choices, saturation points and classification still need verification; no TailBench dependency installation or experiment occurred in this clarification update. Preserve the existing Sysbench pair as the simpler CPU/memory reference.
