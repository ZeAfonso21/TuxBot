# Coordinated multi-application TuxBot

**Implementation only. No tests, benchmarks, tuning sessions, kernel/cgroup writes, or LLM requests have been executed for this extension.** Read-only interface observations are in [KERNEL_COMPATIBILITY.md](KERNEL_COMPATIBILITY.md). Do not run the commands below until the user explicitly authorizes testing on a dedicated experimental host.

## Architecture

One controller implementation, three configurations:

| Mode | Controllers | LLM-visible authority |
|---|---|---|
| `default` | none | none; fresh default cgroups, unchanged host controls |
| `independent` | two conventional Actor/Speculator controllers | each sees only its own objective, baseline, measurements, cgroup endpoints, and history; no shared telemetry/host schema |
| `coordinated` | one Actor/Speculator controller | both applications, their cgroup endpoints, shared telemetry, and approved host controls |

`ScopedController` subclasses the original `SimpleDualLoopOptimizer`. Its dispatch, Actor/Speculator timing, waiting, and final-Actor freeze logic are reused. The legacy source edits are opt-in manager/tuner injection in the constructor and bypassing legacy default discovery during scoped startup, marked `EXTENSION`. Existing users without `_extension_runtime` follow the original path. All new functions/classes are under `src/extension`.

`ScopedTuner` reuses `LLMTuner` client setup, retry policies, provider transport, response timing/token accounting, and API logging. Only prompts, structured schema, strict parsing, and gist behavior change. It deliberately disables legacy scalar Top-N ranking and end-of-run gist calls. The scheduler receives a constant compatibility reward, **not** a new mathematical optimization score; semantic multi-objective decisions use the raw objective vector. Legacy `best_reward`/`best_parameters` are not multi-objective results and must not be used to report success.

`WindowBroker` is a rendezvous, not communication between tuners. Both independent instances run concurrently in separate controller threads with isolated tuners, executors, parameter managers and histories. They never exchange objectives or decisions. Only the experiment coordinator collects the full result. It measures a window exactly once, then projects it into private views. Controller exceptions abort the rendezvous instead of inventing measurements.

The initial runner supports **outside-of-window tuning**: complete the joint measurement, apply the two loops' available decisions, then start the next common window. Both loops remain asynchronous during collection, as in the original architecture. Limiting this first runner to boundary writes makes parameter-to-measurement attribution clearer. Stable windows begin after the final Actor decision for every participating controller.

## Configuration

Examples:

- `src/extension/examples/default.json`
- `src/extension/examples/independent.json`
- `src/extension/examples/coordinated.json`
- Workloads: `src/extension/examples/silo.json`, `src/extension/examples/img-dnn.json`

The examples deliberately set `defaults_verified: false`. The operator must establish actual default kernel settings, default ancestor cgroup settings, controller delegation, workload provisioning, and machine suitability before changing it to true. Capturing the current host does **not** prove it is at kernel defaults. The runner does not impose the legacy hardcoded Linux 5.15 defaults on a newer kernel.

Application fields:

- `id`: unique safe name; exactly two applications per experiment.
- `metric`: key in the measurement reader's JSON.
- `objective`: `minimize` (e.g. latency) or `maximize` (throughput).
- `bound`: positive numeric upper/lower bound according to objective, or `"default"`.
- `priority`: positive numeric relative priority, default `1` (equal). Bounds take precedence.
- `start`, `measure`: trusted operator-authored argv arrays, not model-generated commands.
- `ready_signal`: optional boolean. If true, the server must write the file identified by `TUXBOT_READY_FILE` when ready. All servers must be ready before warmup.

Experiment fields include `warmup_seconds`, `window_seconds`, `tuning_windows`, `stable_windows`, `regression_tolerance` (default 0.05), `regression_windows` (default 3 consecutive windows), `startup_timeout_seconds` (default 300), and `synchronization_timeout_seconds` (default 3600). Provider requests default to 120 seconds per attempt, three attempts; the original final-freeze policy is retained. Allow enough rendezvous time for both models and readers. API credentials remain exclusively in environment variables, never JSON.

`approved_host_parameters` is an operator allowlist, not a promise of availability. Only known fixed interfaces that are readable and writable enter the active host schema. C rejects an empty host surface. Independent tuners receive no host schema even if the experiment coordinator records these values for evaluation. A/B never restore/write host controls; C captures and restores them.

### Cgroup controls

Fresh per-application groups are created beneath an existing **empty, delegated cgroup v2 subtree** with no existing children. Writable `cgroup.kill` is required before launching any workload, and cleanup waits for descendant population to reach zero. The runner never mounts filesystems, invokes sudo, creates systemd units, or migrates the developer shell. A system administrator must provision delegation on the experimental machine. CPU controller availability is mandatory; memory/I/O controllers are enabled if delegated, but only implemented controls are exposed.

- `cpu.weight`: integer 1–10000; relative preference, not a CPU percentage.
- `cpu.max`: `"max 100000"` or `"<quota> 100000"`; fixed period, quota 10000–102400000 microseconds. Quotas can throttle.
- `memory.high`: optional, only with operator-provided safe bounds; reclaim/throttling can still substantially degrade performance. For example:

```json
"cgroup_policy": {
  "application_A": {
    "memory_high_min_bytes": 2147483648,
    "memory_high_max_bytes": 8589934592
  }
}
```

These are illustrative bounds, not workload-safe defaults. Choose page-aligned values with headroom after provisioning. Kernel rounding of non-aligned values fails exact readback and causes rollback.

`memory.max` is deliberately excluded to avoid model-induced OOM. `cpuset.cpus` is excluded until effective CPU/memory-node hierarchy handling is implemented. `io.weight`/`io.max` are not exposed: device/scheduler-specific verification and safe bandwidth bounds are still needed. CPU plus optional soft memory management is the initial useful subset, not a universal cgroup manager.

The server enters its cgroup **before exec**, so forked children inherit membership. This covers normal children, including children that create new process groups. Servers must not move themselves into other cgroups, use external ungrouped services, or delegate work to containers outside this hierarchy. Do not assume grouping a database client also groups its existing PostgreSQL server.

### Existing supported workloads

The bridge in `tailbench.py` reuses `TailbenchBenchmark.pre_execute`, timestamped interval CSV parsing, and `_aggregate_metrics`. The sample pair is **Silo latency minimization + img-dnn throughput maximization**. They require built modified TailBench dependencies, datasets, and workload-specific provisioning. Dependencies were previously found empty; nothing has been downloaded or built here.

The example rates and thread counts are starting values, not validated saturation points. Calibrate the throughput application's offered load before experiments: under a fixed unsaturated arrival rate, reported throughput may simply equal offered load. Hold the chosen rates/data/thread counts constant across A/B/C. Give each run/application a **unique absolute** `tailbench_output_dir`, `results_dir`, and workload config; update both `start` and `measure` to the same config. Never run multiple experimental modes concurrently against the same metric directories.

The bridge intentionally requires timestamped `lats_interval_*.csv` records; it does not use the original overlapping `end + 1 second` selection, log fallback, or modification-time estimates. Records are selected by timestamp in `[start,end)`. Verify actual CSV timestamp convention/timezone and completeness on the experimental build. TailBench p99 remains the **maximum of interval p99s**, not a pooled request p99. The co-located default baseline is the median of three such window values, not a pooled p99 either.

### Other workload reader contract

For any other continuously running workload, `measure` receives:

- `TUXBOT_WINDOW_START`, `TUXBOT_WINDOW_END`: identical wall-clock endpoints for both applications.
- `TUXBOT_APPLICATION_ID`, `TUXBOT_WINDOW_PHASE`.

It must emit exactly one JSON object on stdout, e.g.:

```json
{"window_start": 123.0, "window_end": 133.0, "latency_p99": 4.2}
```

Endpoints must echo the exact provided floats; the metric must be finite and strictly positive. Logs belong on stderr. The reader must actually select data from that interval; endpoint echoing cannot verify workload semantics. Missing, zero, nonfinite, stale endpoint, duplicate-key, process-exit, reader failure, and timeout conditions fail the experiment instead of being treated as valid measurements.

## Future execution (NOT authorized yet)

After explicit user authorization on a dedicated machine:

1. Provision workloads and datasets; configure Gemini credentials (`GEMINI_API_KEY`) for B/C. A requires no key.
2. Provision an empty delegated cgroup root with CPU access; verify default ancestors and host state. Ensure exclusive control of approved knobs; stop unrelated tuners.
3. Use unique run directories, configure workload paths/rates, select safe host controls after reviewing the compatibility report/policy, and set `defaults_verified` only after real verification.
4. Obtain separate permission to run the prepared pure tests before any live experiments. Example future command:

```sh
PYTHONPATH=src python -m unittest extension.test_extension
```

5. Execute each mode separately, repeating/rerandomizing run order as the experimental design requires:

```sh
# FUTURE ONLY: starts real workloads, creates cgroups, and B/C make paid API calls.
PYTHONPATH=src python -m extension.runner src/extension/examples/default.json --authorize-execution
PYTHONPATH=src python -m extension.runner src/extension/examples/independent.json --authorize-execution
PYTHONPATH=src python -m extension.runner src/extension/examples/coordinated.json --authorize-execution
```

6. Inspect restoration results after **every** run. Do not continue after incomplete restoration. Re-establish defaults before the next run.

Per run: capture initial state → start both servers and await readiness → warm up → three default co-located windows → selected tuning/no-tuning phase → frozen stable windows → terminate all workload descendants → restore exact snapshots → remove groups and restore parent subtree controller state.

`results_dir` must not already exist. Ctrl-C/SIGTERM enter cleanup; controllers are joined before restoration. SIGKILL, machine loss, inaccessible interfaces, process migration out of the subtree, and malicious/externally privileged workloads cannot be made safe by Python `finally`. `initial_state.json` persists known original values for manual recovery; there is no automatic privileged recovery daemon. Failed partial cgroup creation is tracked and cleaned up. Root/descendant cleanup or readback failures are reported rather than declared restored.

## Evaluation outputs

Future offline export (does not run workloads or APIs):

```sh
PYTHONPATH=src python -m extension.report \
  results/multi/default-run-1/results.json \
  results/multi/independent-run-1/results.json \
  results/multi/coordinated-run-1/results.json \
  --output results/multi/comparison --plots
```

CSV exports: per-app window trajectories, stable-phase median performance, default-relative factors, constraint violations, significant regressions, inference latency/tokens and decisions, plus per-run experimental success. Optional plots require matplotlib and show each application's cross-mode stable comparison, raw trajectory with violation markers, and normalized trajectory. Raw effective cgroup/host snapshots, per-app cgroup counter endpoints/pressure, shared TuxBot telemetry, provider histories and token information remain in JSON. No model pricing is invented; token usage/latency are supplied, monetary cost is not estimated.

Success is evaluated independently of user bounds: stable-phase median regression beyond tolerance for **either** application makes a complete run experimentally unsuccessful. Bounds may be looser/tighter than that baseline criterion. Stable medians reduce single-window-noise sensitivity; all noisy windows and violations remain visible. `sustained_regression` in controller histories flags consecutive bad tuning windows, including exploration. Automatic restore-to-known-good during tuning is intentionally not implemented; safe coordination with stale model requests would require more scheduler changes. Exact original-state restoration at experiment completion/failure is implemented.

**Interpretation:** C has shared host controls that B deliberately lacks. Compare complete architectures, not contextual awareness in isolation. Do not hide negative results or incomplete runs. No extra experimental configurations are added. Report repetition count, workload load conditions, active schemas, actual phase lengths, percentile semantics, and inference budgets; medians of window metrics are not request-level percentile estimates.

## Limitations / verification handoff

- No empirical acceptance criterion is verified. Prepared unit tests, syntax/import behavior, existing-regression tests, Gemini structured-schema compatibility, dual-loop lifecycle, privileged interfaces, actual readbacks, rollback and signal cleanup all still need authorized testing.
- No Gemini key is required to inspect/edit this implementation or prepare configurations. B/C create clients only during an explicitly gated future execution.
- Scheduler controls may be unavailable on EEVDF. `cstate_max` is excluded; no unverified aliases are invented.
- Shared perf/power sampling reuses the original collectors, including their buffered timing and daemon system-sampler limitations described in `PROJECT_ANALYSIS.md`. Application readers have common exact endpoints; hardware/system samples are not magically perfectly aligned or attributable per application.
- Cgroup counters are saved as before/after cumulative endpoints (CPU time/throttling, memory events/usage, pressure, I/O); consumers must compute deltas/rates, not interpret counters as instantaneous rates.
- TailBench adapter startup/parser APIs and Gemini SDK behavior have only been statically inspected. Timestamped CSV availability, source time convention, throughput saturation, and workload survival under quotas must be verified before claiming usable measurements.
- Independent instances use isolated state within one experiment process, not separate OS processes. The coordinator knows both applications; neither model does. There is no tuner negotiation.
- Operator-authored commands/configurations and cgroup delegation are trusted. The model supplies only validated allowlisted JSON values, never paths or shell commands.

## Source inventory

Legacy modification: `src/optimizer/dual_loop_optimizer.py` (constructor dependency injection and scoped startup bypass of legacy default discovery).

New modules under `src/extension`: `model.py`, `controls.py`, `telemetry.py`, `controller.py`, `host.py`, `runner.py`, `tailbench.py`, `report.py`, `test_extension.py`, and `__init__.py`. Examples and this guide/compatibility review live alongside them. `PROJECT_ANALYSIS.md` receives an append-only implementation note. The pre-existing `.gitignore` modification is unrelated and was left untouched. `PROJECT_ANALYSIS.md` is currently ignored by that file; its appended notes exist on disk but will require explicit inclusion if the handoff is committed.
