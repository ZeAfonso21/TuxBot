# TuxBot extension — current validation status

**Local checkout = source of truth. All execution is remote via `ssh bart 'COMMAND'`.**

**Latest validation (mock-only):** [007 — Attribution fix](../../progress/007-attribution-fix-mocked.md). **57 tests passed** with outbound connections blocked. A deterministic mocked 30/20 loop reproduces 30/30 wrong history labels under the legacy negative control and **0/30** under the corrected scoped controller, including latest/recent and final-Actor prompt checks. C now uses A's complete stable-phase arithmetic means as shared bounds/reference, with actual C startup metrics kept separate. Future windows are **5 seconds**, retaining **30/20**. Mixed windows and mismatched/incomplete A references are rejected. No actual workloads, kernel writes or LLM API calls were performed; no post-fix live improvement is claimed.

**Latest live stage (before this fix):** [006 — Silo/Sysbench](../../progress/006-silo-sysbench.md), [results](../../results/silo-sysbench-01/README.md). TailBench harness/Silo installed; concurrent smoke validated. The first overloaded A candidate was retained and rejected before paid tuning. The completed 1000-request/s pair uses a common A initial-three **arithmetic mean** for both C targets and reporting, with 30/20 windows. **52 extension tests pass**; all 106 successful full-run windows passed the control/telemetry audit, and all workloads/settings/groups were cleaned up/restored. Stable results were negative; no Pareto gain or statistical significance is claimed.

**Previous live stage:** [005 — Relationship batch](../../progress/005-relationship-batch.md), [complete results](../../results/relationships-01/README.md). All three screened relationships qualified; all six no-cgroup-A/scoped-C runs completed with 3/30/20 windows. 48 extension tests passed before execution. All 318 full-run windows passed the final phase/control/telemetry audit; restoration succeeded with no leftover workloads/groups. Stable C gains were negative in every metric; no statistical improvement is claimed. Actual inference usage is recorded with the results.

The sections below retain the **previous offline plotting stage** for historical context. Statements there that no measured no-cgroup A exists or that the runner still groups default A are superseded by stage 005.

## Progress history

- [001 — Initial validation](../../progress/001-remote-validation.md): original tests, schema/model fixes and isolated cgroup smoke check.
- [002 — Historical Sysbench pilot](../../progress/002-sysbench-pilot.md): old grouped-A/C sessions and original artifacts.
- [003 — Run-length clarification](../../progress/003-clarifications-and-experiment-plan.md): 8/3 versus 30/20 and planned coupling studies.
- [004 — Evaluation redesign](../../progress/004-evaluation-redesign.md): new formulas, baseline provenance, four main figures, future configurations and offline-only validation.
- [Current evaluation guide](EVALUATION.md).

## Critical finding: the existing A is not the newly requested A

The historical A used **dedicated default-valued per-workload cgroups**. The new protocol explicitly requires no dedicated workload cgroups. The raw records prove the difference; they were not relabelled or edited.

The report now rejects this historical A by default. `--allow-legacy-a` produces visibly marked historical diagnostics, not a conforming new A/C evaluation. No measured no-cgroup A exists yet. `runner.py` still creates groups in default mode; this execution change was deliberately not made during a plotting-only task. A profiles remain disabled/annotated until that work is separately authorized.

## Latest offline validation

**27 plot/data tests passed** remotely in `src/extension/test_evaluation.py`; the current validation log/JUnit are authoritative. Tests use explicitly synthetic fixtures and optional existing artifact JSON, never native workloads or a tuning controller. They cover:

- Ordinary signed latency reduction / throughput increase, zero current values, missing/invalid references.
- No-cgroup A; contradictory/unknown provenance; tuned or failed A rejection; workload/metric/time mismatch.
- Complete joint CPU/Memory windows, input-order independence, no A/C window-index pairing.
- Stable raw medians before normalization; no invented stable boundary or window pseudo-replication.
- Actual C readbacks rather than proposals; missing/null/mixed histories, discovered knobs/unlimited states and telemetry/control separation.
- Rejected parent aggregate resource scope; never plotting A child-cgroup data as process telemetry.
- Four main PNG/PDF figures, separate optional diagnostics, retired default plots, CSV consistency and unchanged source bytes.
- Explicit 30/20 future profiles and unmeasured workload-pair declarations.

Authoritative artifacts: `results/evaluation-redesign/validation/pytest.log`, `pytest.xml`, and `strict-baseline-check.log`, mirrored locally from bart. Earlier broad/mock/privileged validation is historical; its tuning loops were **not rerun** in this stage. The older mocked-runner test's exporter expectations were updated but not executed under the current restriction.

## Current plots

- **Real historical diagnostics:** `results/evaluation-redesign/historical/`, all marked nonconforming A.
- **Strict-schema synthetic demonstration:** `results/evaluation-redesign/synthetic/`, all marked synthetic.

Each set contains:

1. `relative_improvement.png` / `.pdf` — C relative to fixed A stable medians.
2. `stable_performance.png` / `.pdf` — changes from raw A/C stable aggregates.
3. `applied_parameters.png` / `.pdf` — only actual modified C control histories, grouped by scope/units.
4. `pareto_tradeoffs.png` / `.pdf` — synchronized two-metric windows using the same normalization as Figure 1.

The historical set additionally contains explicitly requested `resource_telemetry`; no A process traces were invented. Old own-baseline/factor/bound-marker/fake-A-cgroup graphs are retired under `results/pilot-01/comparison/retired/`; historical CSV/JSON files remain unchanged.

The historical fixed references are A steady-phase medians: 3.89 ms and 21577.162857 MiB/s. Historical C stable changes are 13.624679% lower CPU latency and 0.847775% higher memory throughput. These are **not new results** and cannot establish the new no-cgroup research comparison. No confidence interval is invented for one run pair. Percentile summaries are not pooled request p99s.

## Future configuration / workload preparation

Generic A/B/C and Sysbench profiles now explicitly request **30 tuning + 20 stable windows**, not yet run. Raw pilot snapshots retain their actual 8/3 configuration and recorded phases.

`examples/workload-pairs.json` contains planned Silo/img-dnn, Xapian/CPU, Sphinx/CPU and Memcached/CPU hypotheses. Added Xapian, Sphinx and CPU-throughput workload definitions reuse existing adapters; they need provisioning, data/storage checks, unique output paths and offered-load calibration. All relationships remain **unmeasured**. Busy-poll socket behavior and a reversible idle-state interface are prerequisites for the proposed network/idle conflict; `cstate_max` remains excluded. No new benchmark dependency was installed.

## Offline-only reproduction

```sh
ssh bart 'cd /work_dir/TuxBot && MPLBACKEND=Agg PYTHONPATH=src /work_dir/tuxbot-venv/bin/python -m pytest -q src/extension/test_evaluation.py'
```

See EVALUATION.md for read-only generation commands. The Python environment is `/work_dir/tuxbot-venv`. Plotting does not need or load the Gemini key; no credits were used in this stage. The protected credential environment file from earlier stages remains outside the repository; no SSH keys/passphrases were accessed.

## Still outstanding

True no-cgroup A execution/capture, real 30/20 datasets, equivalent independent B, new workload provisioning/experiments and classification, repetitions/uncertainty, and live interruption/failure recovery. The existing successful host/cgroup restoration observations belong to the historical pilot, not a new execution in this stage. No new statistical or causal performance claim is made.
