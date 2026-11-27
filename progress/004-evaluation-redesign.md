# 004 — Offline evaluation redesign and future workload templates

## Scope and execution restriction

The user requested a new A/C plotting definition, 30/20 future budgets and additional workload-combination ideas, while explicitly prohibiting new experiments, workloads, tuning loops, cgroups and host-parameter changes. This stage obeys that restriction. Only source/config/docs, synthetic JSON, existing result files, plot tests and offline rendering were used. All Python execution occurred remotely through `ssh bart 'COMMAND'`; local operations were file edits, rsync and image/data inspection. No LLM requests, key loading, native benchmark command, package installation or privileged interface operation was performed.

## Crucial protocol mismatch discovered

The requested A now means **no dedicated per-workload cgroups**. The historical pilot A instead recorded two default-valued child cgroups: initial `cpu.weight`/`cpu.max`, `cgroup_root`, and before/after child samples. It is untuned under the older setup, but it is **not** the newly requested no-cgroup baseline. A mode name cannot override those records.

- The execution path was not changed in this plotting task. Current `runner.py` unconditionally creates groups, so a real no-cgroup A needs a separately reviewed execution change before new experiments.
- A templates are disabled/annotated. Do not make old data "compliant" by changing a JSON flag: contradictory declarations are rejected.
- Strict reporting rejects the old A. The rejection is retained in `results/evaluation-redesign/validation/strict-baseline-check.log`.
- Real old-data figures are available only with explicit `--allow-legacy-a`, labelled **HISTORICAL DIAGNOSTIC ONLY** on every figure and `historical_nonconforming_A` in metadata.
- Separate no-cgroup-schema fixtures are labelled **SYNTHETIC**, never substituted for actual measurements. No new valid A measurement was invented or collected.

This qualification supersedes using the old A/C pilot as evidence for the new topology comparison. Previous stage logs remain historical records of what was executed.

## Implementation

Refactored the existing `extension.report` / `extension.plots` pipeline; no separate plotting stack or new dependencies. `evaluation.py` supplies shared read-only loading, reference aggregation, ordinary percent changes, complete joint-window selection, control readbacks and observed Pareto dominance. `evaluation_fixture.py` supplies explicitly synthetic data without importing any runner or provider.

### Normalization

The single primary reference is each metric's **median across complete joint A stable windows**. Warmup, initial-baseline and tuning windows do not contribute. C's own baseline, TuxBot speedup factors, bounds and rewards are ignored for primary normalization. A and C window indices are not zipped.

- Latency: `100 * (A - C) / A`.
- Throughput: `100 * (C - A) / A`.
- Stable summary: aggregate raw A and C stable values first, then apply the same formula.
- Metric summaries remain window-level summaries; median/max interval p99 is not pooled request p99.

For the reviewed historical data, A references are 3.89 ms and **21577.162857 MiB/s** from windows 9–11, not the initial A memory baseline 21211.454286. Historical stable changes are **13.624679% lower latency** and **0.847775% higher throughput**. These are descriptive and topology-nonconforming, not new experimental evidence. No CI is shown for the one run pair.

### Four main figures

1. `relative_improvement`: C-only CPU/Memory panels against an A zero line. All available non-warmup C samples are retained, with initial C samples shown as unconnected triangles and recorded IDs preserved. Stable shading follows actual phases; missing measurements remain gaps.
2. `stable_performance`: per-metric percent changes from raw stable medians. When explicit independent repetitions exist, points are experiment pairs and whiskers are their observed range—not window-level confidence intervals.
3. `applied_parameters`: C-only discovered modified readbacks, including unchanged per-app counterparts where useful. Numeric times/percentages/weights have separate appropriate panels; unlimited states remain labelled categorical values. Steps use window-start snapshots, initial captures are distinguished, exact write timing is not fabricated, and mixed/missing readbacks are not forward-filled. Proposed settings and memory.current/CPU consumption are never tunables.
4. `pareto_tradeoffs`: the exact same two improvement values from each complete C joint window used by Figure 1. No independently selected app windows. The A origin is a dominance competitor; highlighted points are an observed frontier, not a global optimum.

An optional single `resource_telemetry` figure is opt-in. Host metrics remain shared; old A child-cgroup observations are never plotted as A app telemetry. A needs explicit real process-tree records, which do not exist here. C needs actual child mapping/endpoints or explicit child scope; parent aggregate paths are rejected. memory.current is not a limit or process RSS. The existing old pilot supports host and C-child diagnostics, so this optional figure was generated for the historical set only.

### Integrity and provenance

Mode, completion, tuner/actuation evidence, topology, application identity/metric/direction, workload conditions, time intervals, duplicate IDs and reference validity are checked. Recorded A control changes or tuner records disqualify an untuned reference. Conditions missing from old snapshots require explicit reviewed manifest evidence; native Sysbench headers for both real runs were inspected and agree on version, seed, threads, prime limit and memory operation/size/scope.

`examples/evaluation-pilot.json` contains that review. New producers should capture immutable workload conditions and truthful no-cgroup provenance, rather than merely point at mutable JSON files. Multiple independent repetitions require explicit unique A/C mappings and declarations; one A reused for several C runs is not several independent A/C replications.

Bounds now live separately in `performance_bounds.csv` with direction, numeric bound, origin and violating windows. Raw data/legacy fields are preserved. Missing phases/histories suppress affected figures with recorded reasons, not fake zeros or parameter trajectories.

## Outputs

Source/data contract and commands: `src/extension/EVALUATION.md`.

Current outputs, mirrored locally and on bart:

- `results/evaluation-redesign/historical/`: four main PNG/PDF figures, optional scoped diagnostics, CSVs, `evaluation.json`/`evaluation.md`; all historically qualified.
- `results/evaluation-redesign/synthetic/`: four marked synthetic figures and report tables.
- `results/evaluation-redesign/synthetic-input/`: clearly labelled synthetic source JSON, not workload results.
- `results/evaluation-redesign/validation/`: plot-only test log/JUnit and strict-baseline rejection.

Deprecated own-baseline/speedup/bound-marker/fake-A-cgroup figures are no longer generated by default. The exporter archives known previous generated images under `retired/` instead of deleting raw data or unrelated files. Historical CSV parsing is preserved; report-v2 tables have explicit new semantics and filenames. The old pilot comparison folder is marked as a retired report and points to the new version.

## Future configurations and workload candidates — NOT run

Five experiment profiles now explicitly specify **30 tuning / 20 stable windows**. Raw old pilot snapshots still specify 8/3 and are evaluated according to their actual recorded phases. No source template is used to pretend 30/20 data exist. The A execution/provenance gap blocks a true new A experiment until separately fixed.

`examples/workload-pairs.json` is a non-executable study manifest with unmeasured hypotheses:

- TailBench Silo + img-dnn.
- TailBench Xapian + Sysbench CPU throughput.
- TailBench Sphinx + Sysbench CPU throughput.
- Memcached/Mutilate + CPU as a network/idle-state hypothesis, not an implemented continuous pair yet.

Added Xapian, Sphinx and CPU-throughput workload templates. They reuse existing adapters/reader capabilities, require provisioning, unique paths and saturation/load calibration, and are not presented as measured aligned/conflicting/weakly coupled cases. A fixed low offered load is not a throughput optimization experiment. Busy polling must actually be exercised by sockets/NIC/kernel support. `cstate_max` remains excluded pending a verified reversible interface. No dependencies were installed and no new pair was executed.

The proper classification unit is a **pair + load + control response vector**. The same pair can align for one control and conflict for another. The report does not infer causality or classify a pair from a single favorable result.

## Validation

Only `src/extension/test_evaluation.py` was executed during this stage. It uses synthetic fixtures and optional existing JSON artifacts; it does not import or execute a tuning runner. Coverage includes ordinary signed formulas/zero/missing/invalid references, no-cgroup A, genuine joint timestamps, missing phases/windows, raw stable-median aggregation, arbitrary input ordering, historical A rejection, workload mismatch, actual versus proposed controls, dynamic knob discovery/unlimited values, optional accounting scope, no pseudo-replication, image/CSV generation and immutable raw input files.

The older mocked-runner test's exporter expectations were updated for the new API, but those mock tuning loops were **not rerun** under the current restriction. No claim is made that this stage reran the complete legacy or privileged suite. The final plot-only result is **27 passed**, recorded in the new validation log/JUnit. Initial C samples retain their recorded negative IDs and are not connected in numeric order as a false chronological trajectory.
