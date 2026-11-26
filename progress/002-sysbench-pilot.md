# 002 — Real co-located Sysbench Configuration A / C pilot

## Authorization and scope

The user authorized choosing two workloads, installing their benchmark program on bart, running A first and then C, and generating meaningful plots including improvement per window. All code execution/installations/system changes in this stage occurred remotely via `ssh bart 'COMMAND'` after checking hostname **bart**. Local actions were limited to source/config/document edits, rsync and inspecting copied artifacts. The local checkout remains the source of truth.

This is **one functional pilot pair**, not a completed research evaluation or a statistically established performance improvement. Configuration B was not run in this stage.

## Workload choice and provisioning

Sysbench already has CPU and memory adapters in original TuxBot. Its system package provides both workloads without databases, datasets or compiling empty dependency submodules. Installed on bart with apt: Sysbench **1.0.20** and its package dependencies. TailBench remains unbuilt and is unnecessary for this pair.

The user installed `linux-tools-5.15.0-89-lowlatency`; verified `perf version 5.15.126`, matching the target's Linux 5.15 family. A short hardware-counter check succeeded before the experiment. No perf permissions/sysctls were weakened.

Machine: Intel Xeon E3-1265L V2, 4 physical cores / 8 logical CPUs, 8 MiB LLC, approximately 15 GiB RAM. It was idle before provisioning/preflight. Both applications use the same unrestricted 0–7 logical-CPU availability, not separate CPU partitions.

| Application | Workload | Stress point | Objective |
|---|---|---|---|
| `cpu_latency` | `sysbench cpu`, 4 threads, max prime 20000 | Prime computation / CPU scheduling | Minimize `latency_p99_ms` |
| `memory_bandwidth` | `sysbench memory`, 4 threads, private 256 MiB buffers, sequential reads | 1 GiB aggregate working set, beyond the 8 MiB LLC; memory bandwidth/cache contention | Maximize `throughput_mib_s` |

The large `memory-total-size` limits **bytes processed**, not allocation; resident buffers total about 1 GiB. Both applications run continuously with one-second reports; no per-window restart or database service is involved. Seed, thread count, working set, operation and offered conditions are identical between A and C.

A four-second simultaneous preflight recorded CPU tail-latency and approximately 21–22 thousand MiB/s memory throughput. Preflight output remains on bart under `results/sysbench-preflight/`; it is not the measured A baseline.

## Implementation added/fixed

- `src/extension/sysbench.py`: a small continuous CPU/memory bridge. The original adapter restarts Sysbench per window and parses final summaries, so it cannot directly supply aligned observations for two persistent applications. This bridge parses real one-second reports and reuses the existing extension reader contract. It is application-metric plumbing, not another OS monitoring framework.
- Complete reports are selected **within the same common window endpoints**. Timestamping uses wall-clock receipt time, with interval lengths taken from Sysbench elapsed seconds. The line-buffered `stdbuf -oL` bridge limits buffering; this is still receipt-time alignment, not reconstructed per-request timestamps. Partial final JSONL records are excluded, malformed complete records fail, and too few complete intervals fail.
- CPU window metric: **maximum of contained one-second p99 values**. Baseline: median of three such window metrics. Stable result: median of three stable-window metrics. None of these are pooled request p99 estimates.
- Memory window metric: arithmetic mean of contained one-second MiB/s rates.
- `cgroup_deltas` in `telemetry.py`: CPU time in core-equivalents, throttling deltas, memory usage, pressure-time deltas, while preserving raw before/after counters.
- Optional `require_perf_metrics` fails on missing IPC rather than silently accepting a telemetry-free run. Existing TuxBot perf/system collectors remain responsible for hardware counters, CPU load and RAPL power.
- Optional `host_limits` can only narrow verified bounds. Pilot C's scheduler and Intel P-state ranges were narrowed to avoid extreme exploratory settings. Busy polling is irrelevant here and was not exposed; `cstate_max` remains unsupported.
- `pilot.py`: explicitly gated, hostname-checked supervisor, expected-initial-host checks, temporary CPU delegation, fresh default cgroup-root checks, child runner execution and restoration verification. It checks original tunable readbacks again after completion. State evidence is persisted before delegation changes.
- `plots.py` + `report.py`: persistent relative-improvement, common-A-reference, hardware/resource and actual-control trajectories; CSV values preserve explicit objectives, factors, percentages and constraint violations. CPU-load plots use a 0–105% scale rather than visually magnifying tiny fluctuations near 100%. Figures are saved with complete titles as PNG/PDF.

### Failure retained and corrected

The first A attempt (`results/pilot-01/A-default/`, `A-default.log`) stopped **before starting either workload**: `Windows` inherited an abstract `cleanup` requirement but did not implement it. Mocking the collector in earlier runner tests had hidden this issue. Added the lifecycle-owned no-op method and a regression test constructing the real collector. Initial state/delegation were restored without errors. The successful retry uses a new directory, `A-default-02`; no failed output was overwritten.

Final targeted suite: **23 passed** (initial 16 plus Sysbench/rates/ranges/concrete-collector/hostname tests). Actual suite and JUnit artifacts: `results/pilot-01/validation/pytest.log`, `pytest.xml`. Tests and plots were executed remotely, not locally.

## Protocol actually executed

Each run:

1. Verify hostname and all six approved host controls against expected captured defaults: scheduler min granularity 3000000 ns, latency 24000000 ns, wakeup granularity 4000000 ns, migration cost 500000 ns, Intel min/max percentages 45/100.
2. Record parent-controller state (`memory pids`), temporarily enable CPU delegation and create a fresh empty experiment root. Check its `cpu.max`, `cpu.weight`, `memory.high` and `memory.max` are default/unlimited as applicable. Neither app uses hard memory limits.
3. Start both applications in their own cgroups, wait for real reports/readiness, then warm up 10 seconds.
4. Collect **three simultaneous 8-second default windows** and store each application's median baseline.
5. Execute **eight 8-second windows**: unchanged defaults in A; the original dual-loop scheduler plus coordinated proposals in C. C applies validated changes at boundaries, not during collection.
6. Execute **three 8-second stable windows**. C refreshes its final Actor decision before this phase and freezes controls.
7. Stop all workload descendants; restore original app/host values; remove the experiment root; restore the ancestor controller set; verify post-run host readbacks.

Both successful runs contain **14 measured windows**. A lasted about **126.33 s**, C **156.04 s**, including setup/warmup/model overhead. They do **not** have equal total load exposure/wall time: workloads continue during C's inference waits. Keep this distinction in later methodology.

C used Gemini **3.5 Flash** as Actor and **3.5 Flash-Lite** as Speculator. There were **17 successful validated proposals**: 8 Speculator and 9 Actor (including final freeze), with no recorded actuation errors. Proposals included real host and cgroup controls, not just dry-run JSON.

Final C measured controls include CPU weights 500/100, scheduler min granularity/latency/wakeup granularity 1000000/8000000/1000000 ns, migration cost 500000 ns, and Intel minimum/maximum 95/100. Original values were restored afterward; repeated parameter reassertions are still counted as decisions, not independent improvements.

## Observed performance

Stable values are medians of the **three stable window metrics**, not averages across independent repetitions.

| Metric | A baseline | A stable median | C baseline | C stable median |
|---|---:|---:|---:|---:|
| CPU max-interval-p99 latency (ms), lower better | 3.89 | 3.89 | 3.89 | 3.36 |
| Memory read throughput (MiB/s), higher better | 21211.45 | 21577.16 | 21540.66 | 21760.09 |

Compared with A's stable median:

- CPU latency was **13.62% lower**; the default-relative ratio factor was **1.1577**, or **+15.77% ratio-based improvement**. These two percentages are not interchangeable.
- Memory throughput was **0.85% higher**, a factor of **1.0085**. This is a small observation likely within run-to-run variability without repetitions.

Normalized to each run's **own measured baseline**, C's stable factors were **1.1577** and **1.0102** respectively. The A/C memory baselines differed by about 1.55%; plots explicitly offer both own-baseline and shared-A-reference normalization instead of hiding this drift.

C had no measured post-baseline bound-violating windows for either app. A had four CPU-bound violations and two memory-bound violations, spread across four windows; none exceeded the 5% significant-regression threshold. This illustrates why strict per-window bounds, stable-median bounds and noise-tolerant experimental success are recorded separately. `evaluation.csv` identifies the stable-median evaluation and adds an all-windows flag; it does not pretend A never had a noisy violating window.

The performance curve is **not monotonic**: CPU improvement fell back to baseline in C windows 6–7 before recovering. Plots show every actual window, not best-so-far selection or smoothing. Do not attribute the gains to one specific control or to contextual awareness without further evidence.

## Telemetry and restoration validation

In **all 14 windows of both runs**, IPC, cycles, instructions, cache-miss count, socket CPU load and socket RAPL power were present. Raw perf outputs and incremental system-sample files are retained. These are shared-host measurements, not hardware counters uniquely attributable to each application.

Cgroup observations show roughly four CPU core-equivalents per app; CPU workload memory is about 10 MiB, memory workload about 1.04 GiB. CPU pressure/throttling and memory/I/O pressure endpoints/deltas are recorded. This verifies two distinct grouped workloads rather than measuring an ungrouped client while its server runs elsewhere.

Readbacks show configurations constant within every measurement window, and constant across each stable phase. Both runs restored the exact selected host/app snapshots and original `memory pids` delegation with no reported errors. A post-run check found no `tuxbot-pilot-*` roots or remaining Sysbench CPU/memory processes. Installed benchmark packages intentionally remain installed.

## Model usage

C's recorded successful decisions used:

- Input: **445546 tokens**.
- Output: **4876 tokens**.
- Thinking: **12748 tokens**.
- Reported billable total: **463170 tokens**.
- Sum of successful inference response times: about **103.06 s**; calls overlap, so this is not total added wall time.

No euro price, remaining balance, or invoice total was guessed. The supplied key was loaded only remotely from the protected environment file and was not displayed. A remote artifact scan confirmed the actual key bytes do not occur in the copied pilot files. No SSH private keys/passphrases were accessed.

Prompt size reached about 52k input tokens on the final Actor call because recent history includes verbose raw telemetry. History compaction is a possible later cost/latency improvement; it was not silently changed during the experiment.

## Artifacts and plotting logic

Identical copies now exist under local `results/pilot-01/` and remote `/work_dir/TuxBot/results/pilot-01/` (about 3.4 MiB when copied). Existing Git ignore rules exclude this data, so commit progress notes/code separately from raw artifacts if desired.

Main figures in `results/pilot-01/comparison/`:

- `improvement_per_window.png` / `.pdf`: ratio-based percent improvement, relative to each run's own concurrent baseline. Above zero means improvement. Windows 9–11 are shaded stable windows.
- `improvement_vs_configuration_A.png` / `.pdf`: both runs normalized to the single A baseline. This preserves differences in baseline drift.
- `cpu_latency.png`, `memory_bandwidth.png`: stable raw comparisons, raw trajectories with bound-violation markers and factor trajectories.
- `host_telemetry.png` / `.pdf`: CPU load, IPC, package power.
- `application_resources.png` / `.pdf`: actual cgroup CPU-time rates and memory usage.
- `control_trajectory.png` / `.pdf`: measured **window-start** readbacks, not later decisions incorrectly attributed to the earlier measurement.

Tables: `trajectories.csv`, `stable.csv`, `decisions.csv`, `controls.csv`, `evaluation.csv`, `pilot-summary.json`. Raw data: each run's `results.json`, `baseline.json`, Sysbench interval JSONL/logs, `telemetry/`, C's provider/history logs, and sibling `.delegation.json` evidence. Failed A setup files remain alongside them.

Plot/export logic lives in `src/extension/report.py` and `src/extension/plots.py`. The mocked-test figures previously mentioned were deleted with their temporary directories; the files above are now retained **real experiment** figures, visually inspected after generation.

## Reproduction and next steps

Configs: `src/extension/examples/pilot-A.json`, `pilot-C.json` and matching `sysbench-{cpu,memory}-{A,C}.json`. Current output directories already exist, so **copy/update run IDs and both metric paths before another live run**; the runner refuses overwriting data. The pilot wrapper is bart-specific and requires the expected initial values to match; do not force-write mismatches to make it start.

Commands used (not instructions to rerun automatically):

```sh
ssh bart 'cd /work_dir/TuxBot && OS_PARAM_TUNING_ROOT=/work_dir/TuxBot PYTHONPATH=src /work_dir/tuxbot-venv/bin/python -m extension.pilot src/extension/examples/pilot-A.json --authorize-execution --expected-host bart'
ssh bart '. /work_dir/.secrets/gemini.env; cd /work_dir/TuxBot && OS_PARAM_TUNING_ROOT=/work_dir/TuxBot PYTHONPATH=src /work_dir/tuxbot-venv/bin/python -m extension.pilot src/extension/examples/pilot-C.json --authorize-execution --expected-host bart'
```

Safe offline regeneration (still executed remotely):

```sh
ssh bart 'cd /work_dir/TuxBot && MPLBACKEND=Agg PYTHONPATH=src /work_dir/tuxbot-venv/bin/python -m extension.report results/pilot-01/A-default-02/results.json results/pilot-01/C-coordinated/results.json --output results/pilot-01/comparison --plots'
```

Remaining: repeated/rerandomized A/C measurements, equivalent independent-mode B, further window/percentile validation, live interruption/failure recovery under tuning, other cgroup controls if needed, and a justified statistical evaluation. No single pilot proves general coordinated superiority. C also intentionally has host controls unavailable to B, so future B/C comparisons concern complete architectures, not contextual awareness alone.
