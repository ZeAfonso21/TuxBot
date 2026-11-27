# TailBench/Silo installation on bart

## Installed

- Source: `https://github.com/gliargovas/Tailbench.git`, pinned project revision `2f3098b539a9a3413086fc77e29637937bafd116`.
- Location: `/work_dir/tailbench-src/`.
- Filtered sparse checkout: `tailbench/harness`, `tailbench/silo`, plus their ancestor/root files. Other TailBench applications and their datasets are **not installed**.
- Native binary: `/work_dir/tailbench-src/tailbench/silo/out-perf.masstree/benchmarks/dbtest_integrated`.
- Clean native build with GCC/G++ 11.4, two compilation jobs, jemalloc and bundled LZ4. No application source patch was required. Compiler warnings are retained in `build.log`.
- Total checkout/build approximately 105 MiB; approximately 2.7 GiB disk space remains. Silo generates its TPC-C data in memory, so no 10.23 GB TailBench input archive was downloaded.
- Commit, executable SHA256, resolved libraries, package versions and host readbacks: `provenance.json`. Dependencies were installed with apt; commands/output are in `apt-*.log`.

## Concurrent smoke test passed

Foreground execution through SSH, using the existing benchmark/collector classes:

- Silo: TPC-C workload, scale factor 4, four worker threads, 1000 offered requests/s, 1000 warmup requests, one-second latency reports.
- Sysbench CPU: four threads, prime limit **50000**, objective **events/s**.
- After both were reporting and an additional 10 seconds warmup, collected three shared eight-second windows.

| Window | Silo p99 summary (ms) | Sysbench CPU (events/s) |
|---|---:|---:|
| 1 | 0.313 | 370.427143 |
| 2 | 0.324 | 370.427143 |
| 3 | 0.300 | 370.142857 |
| Arithmetic mean | **0.312333** | **370.332381** |

Silo's per-window summary is the maximum contained interval p99, not pooled request p99. The displayed arithmetic mean averages the three window summaries. This is an installation/metric-collection smoke test, **not the 30-tuning/20-stable A/C evaluation**, and does not establish a conflicting response or optimization improvement. Offered-load calibration is still required.

Native output, interval CSVs, Sysbench interval JSONL, telemetry and JSON results are under `smoke-02/`. All three windows have positive host instructions/cycles/IPC/RAPL data. No cgroups or OS tuning controls were written. Host tunables remained at the recorded values and root delegation remained `memory pids`. Both native processes were stopped and no workload remained. No paid model call or API-key loading occurred.

## Output-directory compatibility

The pinned harness ignores `TBENCH_OUTPUT_DIR` for its interval files and writes `lats_interval_*.csv` into its current working directory. The first smoke attempt therefore timed out waiting in the configured output folder; Silo itself was running and emitted metrics in the source working directory. Its failed JSON and log are retained under `smoke-01/` and `smoke-attempt-01.log`.

The successful attempt uses an isolated per-run working directory (`smoke-02/runtime/silo/`) with symlinks to the installed binary directory and bundled dependency directory. `tailbench_root` points to that run's `runtime/`, and `tailbench_output_dir` matches its `silo/` directory. This keeps native outputs isolated and lets the existing collector find them without changing benchmark source.

The execution recipe is `smoke.py`; the original failed recipe is `smoke-attempt-01.py`. Artifacts were synchronized with rsync over SSH because SSHFS refused to read the absolute runtime symlinks.

## Prerequisites identified before the full paired benchmark

**Subsequently resolved for the completed run:** see [experiment results](../README.md). The extension now has graceful native cleanup and an opt-in common A initial-mean reference. The paragraphs below describe the limitations found during installation, before those corrections.

The existing TailBench adapter starts its native process in a separate session. The no-cgroup A runner currently kills the outer bridge's process group, which alone would not terminate native Silo. The smoke test explicitly called the adapter's cleanup in `finally`; equivalent scoped native cleanup is necessary for the full A/C run.

The requested shared reference protocol (arithmetic mean of A's first three windows, used for both tuning targets and reporting) also differs from the current runner/report defaults (C-own initial medians / A stable medians). Those defaults were **not silently used for a new full benchmark**. No application/optimizer code was changed during this installation.
