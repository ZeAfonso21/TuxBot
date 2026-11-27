# 006 — TailBench installation and completed Silo/Sysbench experiment

Summary and artifact index: [results/silo-sysbench-01/README.md](../results/silo-sysbench-01/README.md).

## Provisioning

Installed the pinned TailBench revision `2f3098b539a9a3413086fc77e29637937bafd116` on bart under `/work_dir/tailbench-src`, using a filtered sparse checkout of the harness and Silo. Native compilation used GCC 11.4 and two jobs; approximately 105 MiB for checkout/build. Only needed dependencies were installed. Other TailBench applications/large input datasets were not installed. No benchmark source patch was required.

A first concurrent smoke test timed out because the harness writes interval CSVs to cwd, ignoring the adapter's output environment variable. Its files/log are retained. Isolated per-run native working directories with symlinks to the installed binary/dependency directories resolved that mismatch. A second concurrent Silo/Sysbench smoke test passed, with no tuning/API calls. Installation records are under `install/`.

## Protocol and safety corrections before the full run

Kept the existing dual-loop search algorithm. Extension-only changes add an opt-in arithmetic mean of three initial windows and a completed/validated shared A reference (`reference_run`). C records that source hash and uses the same numeric targets as reporting. Reports recognize that proof and refuse a conflicting reference policy; older datasets retain their original median treatment.

SIGTERM now enters the TailBench bridge's cleanup; the no-cgroup A runner waits for native cleanup before final process-group cleanup. This matters because the adapter starts native Silo in its own session. Added four focused regression tests; the **52-test extension suite passed** remotely before execution and after offline export refinements.

## Actual runs

All work ran **in the foreground through SSH**, with tee/pipefail logs and rsync synchronization. Models: Flash Actor / Flash-Lite Speculator, after the user confirmed credits had reset.

- First A candidate: Silo 4 workers / 10000 requests/s / scale factor 4 plus Sysbench CPU 8 threads / prime limit 50000. Full untuned A completed, but its latency queue grew; the predeclared stationarity gate rejected it before any paid C call. Raw measurements were retained, not overwritten.
- Completed pair: same programs, threads, scale and objectives, with **1000 Silo requests/s**, no CPU affinity partitioning. A and C each collected **3 initial + 30 comparison/tuning + 20 stable** eight-second windows after readiness and 20 seconds warmup.
- A had no dedicated workload cgroups and no OS knob initialization/writes. C used per-workload CPU weights/quotas and the six verified host controls.

Shared A initial-three arithmetic means: **0.3893333333 ms Silo latency summary; 611.4290476190 Sysbench events/s**. C's 20-window stable arithmetic means: **0.504150 ms / 611.3424285714 events/s**, corresponding to **−29.490582% latency reduction / −0.014167% throughput improvement**. No Pareto improvement was observed. A's later untuned latency mean was 0.456350 ms, demonstrating drift/noise relative to the short initial reference. No statistical/causal claim follows from one sequential pair.

This is the requested heterogeneous pair, but a conflicting relationship at the completed load was not independently proven by a controlled knob sweep. No extra paid screening calls were made. Silo summaries are maxima of timestamp-selected interval p99s, not pooled request p99; native CSV timestamp resolution is one second.

All 106 successful full-run windows have positive shared IPC/instructions/cycles/RAPL; controls are constant within windows and frozen across each stable phase. All restoration errors are empty, original host values and root `memory pids` delegation were restored, and no Silo/Sysbench/group remained. Exact audit: `run-02/final-audit.json`.

The four main PNG/PDF figures, optional scoped telemetry, CSVs, raw native logs, input JSONs, source hashes and foreground logs are in `run-02/`. C recorded 30 Speculator + 31 Actor decisions and 3,376,467 reported billable tokens; monetary billing is not independently verified.
