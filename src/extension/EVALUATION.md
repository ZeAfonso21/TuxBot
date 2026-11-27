# A vs C evaluation report (version 2)

This is a **read-only plotting/data-validation pipeline**. It never imports an optimizer, launches a workload, creates a cgroup, changes kernel parameters or calls an LLM. All execution, including plotting tests, is performed on bart through SSH. The local checkout remains the source of truth.

## Current initial-mean protocol (Silo/Sysbench run-02)

The completed [Silo/Sysbench experiment](../../results/silo-sysbench-01/README.md) uses `baseline_aggregation: "mean"` in A/C and `reference_run: ".../A/results.json"` in C. The loader validates a completed untuned no-cgroup A, matching workload conditions/metrics and unchanged captured host settings. C records A's source hash and the arithmetic means of its three initial windows. Those same values set C's default bounds and every report reference; C's own initial measurements remain separately recorded diagnostics.

Reports detect this proof automatically, or accept `reference_policy: "initial_mean"` in an explicit pair manifest. They reject mismatched hashes/values or a request to silently substitute a stable-median reference. C's stable summary uses the mean of its complete joint stable windows before calculating percentages. Historical experiments without this opt-in retain the original stable-median policy described below; no raw history was rewritten.

## Historical baseline/protocol finding

The requested A is **untuned concurrent workloads without dedicated workload cgroups**. The existing pilot A JSON instead contains `cgroup_root`, two initial `application_updates` maps and per-child cgroup samples. Its groups had default values, but that does **not** make it a no-cgroup baseline. The report refuses it by default.

At the offline-redesign stage, no protocol-conforming measured A was available. Outputs from that stage:

- `results/evaluation-redesign/historical/`: four main figures and an explicitly requested optional diagnostic, generated from the real old pilot using `--allow-legacy-a`. Every figure is marked **HISTORICAL DIAGNOSTIC ONLY** and metadata says `historical_nonconforming_A`. These are not evidence for the new no-cgroup comparison.
- `results/evaluation-redesign/synthetic/`: four main figures from explicitly synthetic fixtures with a no-cgroup A schema. Every figure is marked **SYNTHETIC**. These demonstrate rendering/validation, not experiment results.
- No raw historical measurement was edited, relabelled, or replaced by synthetic data. No new experiments were run during that offline stage.

The current `runner.py` still creates per-app groups in default mode. It was **not changed** in this plotting task, per the execution-logic restriction. Implementing the true no-cgroup A path requires a separate execution change before future live evaluation. The A template remains disabled (`defaults_verified=false`). Changing JSON provenance alone cannot make old grouped data compliant: contradictory declarations are rejected.

## Inputs and data contract

`evaluation.py` reads the existing extension `results.json`: `mode`, `completed`, `config`, `applications`, and joint `windows` containing `window`, `phase`, `start`, `end` and per-app `current` metrics. Existing serialized `baseline`, `improvement`, `reward` and performance bounds are **not** primary normalization inputs.

Each run must identify the same two app IDs, metric names and optimization directions. App-array order does not pair metrics: the known Sysbench CPU/Memory metrics determine their display order. Each joint window has one common time interval; when readers record `raw.window_start/window_end`, both must match that interval exactly. Duplicate IDs, overlapping within-run windows and inconsistent endpoints are rejected. Missing/invalid measurements stay absent, not zero. Zero current throughput can legitimately represent a complete outage; a zero A reference cannot define percent improvement.

For new data, the following are **metadata contract examples, not observations or implemented execution changes**:

```json
{
  "provenance": {"dedicated_workload_cgroups": false, "concurrent_workloads": true},
  "config": {
    "workload_conditions": {
      "cpu_latency": {"program": "sysbench", "workload": "cpu", "threads": 4, "cpu_max_prime": 20000},
      "memory_bandwidth": {"program": "sysbench", "workload": "memory", "threads": 4, "block_size_kib": 262144, "scope": "local", "operation": "read"}
    }
  }
}
```

Do not put false no-cgroup metadata on actual grouped data. Future run capture should include immutable workload settings/build/data identifiers, not just references to mutable configuration filenames.

If conditions were not embedded, use an explicit pair manifest with `conditions_verified=true`, a structured shared `workload_conditions` map and nonempty `conditions_evidence` describing an actual offline review. `examples/evaluation-pilot.json` records reviewed native Sysbench headers (same 1.0.20 version, seed, threads, prime limit, block size, local/read operation and transfer target). It does not claim those settings were embedded at runtime. The A/C measurement/warmup durations must match when recorded.

## Reference and formulas

For each explicit run pair:

1. Select A rows whose **recorded phase is `stable`**.
2. Keep complete joint rows containing both app metrics from that same interval.
3. Compute each metric's median across those rows. This fixed representative A value is used for **all** plotted C windows.
4. Exclude warmup, initial-baseline and tuning rows from this A reference. No time/window-index pairing between independent A and C runs is assumed.

For latency: `100 * (A_latency - C_latency) / A_latency`.

For throughput: `100 * (C_throughput - A_throughput) / A_throughput`.

Positive is improvement; negative is regression. Latency reduction is **not** `A/C - 1`. For example 4 → 3.2 ms is 20% lower latency, not 25% speedup-factor improvement.

The stable summary separately computes raw A and C stable medians first, then applies these formulas. It never averages window-level percentages. Current Sysbench latency is a **maximum of contained interval p99s**; medians of these summaries are **not pooled request p99s**.

Missing stable phases do not trigger an invented stable phase or an automatic own-baseline fallback. Missing joint stable rows are excluded for both metrics together and their IDs/counts are reported. Count mismatches remain visible. With no usable A stable reference, performance plots are skipped; actual C parameter histories may still be rendered.

For the old pilot only, the reviewed A stable reference is **3.89 ms / 21577.162857 MiB/s**, selected from actual windows 9–11, not the initial three-window memory baseline 21211.454286. C stable medians are 3.36 ms / 21760.088571 MiB/s. This produces descriptive historical improvements **13.624679% / 0.847775%**, subject to the topology caveat above.

## Four default figures

| File (PNG + vector PDF) | Source and meaning |
|---|---|
| `relative_improvement` | Two stacked CPU/Memory panels, all available non-warmup C observations versus fixed A stable references. Initial C samples use unconnected triangles; tuning/stable samples form the trajectory. A appears only as 0%, never an improving trajectory. Gaps remain gaps. Stable regions come from recorded phases, not a hardcoded boundary. |
| `stable_performance` | Per-pair raw A/C stable medians converted to ordinary percent change. With one pair, descriptive bars/points and no CI. With independent repetitions, points are run pairs, center is their median improvement, whiskers show the observed run-pair range—not a confidence interval. |
| `applied_parameters` | C only: actual modified controls discovered in window-start readbacks, separated by scope and comparable units. Unchanged app counterparts are included when the same knob changes in the other app. Step plots, captured initial references and missing-data gaps; never LLM proposals or telemetry. |
| `pareto_tradeoffs` | The exact same normalized C joint-window observations used in Figure 1, never CPU and Memory values from different windows. Upper right benefits both. An observed nondominated frontier includes the A origin as a competitor; it is not a global/Pareto-optimality guarantee. |

Titles use the requested Configuration A — Untuned / Configuration C — Coordinated names. Paths, IDs, SHA256 hashes, selected window IDs, phase counts, warmup/duration, reference values and quality notes live in `evaluation.json`/`evaluation.md`, not cluttered legends. Negative improvements remain below zero and percent axes include zero. No best-so-far smoothing or unexplained bound markers are used.

## Applied parameters versus observations

`configuration_start.application_updates` and `.host_updates` are captured by the scoped actuator's actual reads. `observed_host_start` is an additional host readback. When both disagree, host plotting is suppressed and flagged. If start/end configurations differ within a measurement window, that window is excluded from constant-configuration step series rather than falsely attributing a single setting to the whole interval.

The producer used negative IDs -1/-2/-3 for initial C samples in reverse numeric chronology. Those IDs are preserved, and the initial samples are deliberately not joined by a chronological line. They are normalized to A's stable reference, never to themselves. Parameter steps focus on tuning/stable windows with captured initial defaults provided separately.

Steps connect **window-start snapshots**, not invented precise application times. Baseline snapshots in `initial_configuration` can be shown as dotted initial references. Missing histories are not forward-filled. A proposed-only setting in `decisions.proposal` is never evidence that the kernel accepted it. Missing applied histories cause the parameter figure to be skipped and documented, not fabricated.

`cpu.weight`, `cpu.max`, `memory.high` are configured controls. `memory.current`, CPU-time rates and pressure are observations and are explicitly excluded. Numeric scheduler times are converted ns → ms together; P-state percentages and CPU weights have separate panels. Unknown numeric controls get their own raw-unit panel. Unlimited/non-numeric states (`max`, compound `cpu.max`) remain labelled categorical states rather than fictional numeric percentages. Knob availability is never assumed from a hardcoded list; unit classification is separate from actual history discovery. The synthetic fixture includes an intentionally unknown key to test raw-unit fallback; it is not an implemented/approved tuning control and never appears in the real historical parameter figure.

The historical data have actual changes in CPU weight, four scheduler controls and minimum Intel P-state percentage. Maximum percentage and CPU quotas were unchanged and are omitted, except an unchanged app weight remains as a labelled comparator. No A parameter/cgroup series is produced.

## Optional diagnostics

`--telemetry` requests **one separate** `resource_telemetry` figure, only when usable observations exist. It is not generated by default.

- Host CPU load, IPC and package power remain shared-host metrics, not per-app hardware attribution.
- A process accounting requires explicit `resource_scope.kind=process_tree` and real `process_window.cpu_usage_cores` / `memory_rss_bytes` records. The old A has no such records, so no A app resource trace is invented—even though its historical cgroup data exist.
- C resources use a verified child mapping (`cgroup_root/app_id` plus actual endpoint/readback records) or explicit child-cgroup scope. Parent aggregate paths are rejected. `memory.current` is labelled cgroup memory charge, not RSS or a configured limit.
- Process RSS and cgroup memory.current are different semantics and are not merged onto the same numeric panel. Core-equivalents are CPU-time delta divided by elapsed wall time, not a percent. Perf IPC may be rounded by the original parser.
- Diagnostics do not imply that utilization/power directly determines latency or throughput. Missing/unreliably scoped data are omitted; if nothing reliable exists the figure is skipped with a reason.

## Repetitions

Exactly one A/C pair can be passed as two input paths when workload conditions are embedded. Multiple repetitions require `--pairs manifest.json` with an explicit A/C mapping per pair, unique IDs/artifacts, identical recorded/reviewed workload conditions and `independent_repetition=true`. Reusing one A run for several C runs does not create independent A/C repetitions. File paths/window indices are not silently zipped. No window-level bootstrap is presented as experiment-level uncertainty.

## CSVs and retirement

- `relative_improvement.csv`, `stable_summary.csv`, `paired_summary.csv`, `pareto_points.csv` contain the single A-reference evaluation.
- `applied_controls.csv` contains C readbacks, scope, app, actual initial value and whether the series changed.
- `raw_metrics.csv` retains all parsed phases and missing values; raw source files are never modified.
- `performance_bounds.csv` separately identifies metric, direction, numeric bound, its origin and violating windows. A run's own default-derived bound is not the A evaluation reference.
- `inference.csv` preserves proposal/timing/token bookkeeping as such, not as applied controls.

Own-baseline curves, speedup-factor percentages, raw/bound-marker composites and fake A cgroup telemetry are **retired from default output**. On regeneration, known old/generated image files are moved under `retired/` without deleting raw JSON or arbitrary files. Old input JSON remains readable. Legacy performance CSV/image semantics must not be mixed with report-v2 percentages. Prior experiment notes remain historical records, not the current report definition.

## Offline-only commands

No key is needed; no experimental command is used:

```sh
# Historical real data, with the protocol mismatch explicitly acknowledged on every figure.
ssh bart 'cd /work_dir/TuxBot && MPLBACKEND=Agg PYTHONPATH=src /work_dir/tuxbot-venv/bin/python -m extension.report --pairs src/extension/examples/evaluation-pilot.json --allow-legacy-a --output results/evaluation-redesign/historical --plots --telemetry'

# Strict-protocol synthetic demo, NOT experimental evidence.
ssh bart 'cd /work_dir/TuxBot && PYTHONPATH=src /work_dir/tuxbot-venv/bin/python -m extension.evaluation_fixture --output results/evaluation-redesign/synthetic-input'
ssh bart 'cd /work_dir/TuxBot && MPLBACKEND=Agg PYTHONPATH=src /work_dir/tuxbot-venv/bin/python -m extension.report results/evaluation-redesign/synthetic-input/A-synthetic.json results/evaluation-redesign/synthetic-input/C-synthetic.json --output results/evaluation-redesign/synthetic --plots'

# Plot/data tests only, no mocked tuning loops, workload launches or privileged interfaces.
ssh bart 'cd /work_dir/TuxBot && MPLBACKEND=Agg PYTHONPATH=src /work_dir/tuxbot-venv/bin/python -m pytest -q src/extension/test_evaluation.py'
```

## Future experiment configuration (not executed here)

Generic A/B/C and Sysbench profiles now explicitly specify **30 tuning + 20 stable windows**. Existing raw pilot snapshots remain 8/3 and are plotted as recorded, not stretched into 30/20. `examples/workload-pairs.json` adds unmeasured candidate pairings across TailBench/Sysbench and the Memcached/Mutilate hypothesis; Xapian, Sphinx and CPU-throughput workload templates are present. They need provisioning, unique output paths and load calibration; they are not labelled aligned/conflicting/weakly coupled before measurements.

The busy-poll/shallow-idle hypothesis also needs real socket/NIC behavior verified; busy_poll can be ineffective if the application never exercises it. `cstate_max` is still excluded without a reversible validated interface. No benchmark installation, probe, pairing experiment, API request or system modification was performed in this plotting stage.
