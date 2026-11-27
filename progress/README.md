# TuxBot extension progress

The local checkout is the source of truth; source/results are mirrored with bart. All Python execution/installations/workloads/tuning occur only through `ssh bart 'COMMAND'`. **Latest stage: attribution corrected and 57 mock-only tests passed; future protocol is A stable means and five-second 30/20 windows. No live post-fix experiment has run.**

- [001 — Initial remote validation](001-remote-validation.md)
- [002 — Historical grouped-A/C Sysbench pilot](002-sysbench-pilot.md)
- [003 — Run counts, colors and next study](003-clarifications-and-experiment-plan.md)
- [004 — Evaluation redesign and provenance](004-evaluation-redesign.md)
- [005 — Completed real relationship batch](005-relationship-batch.md)
- [006 — TailBench/Silo installation and Silo/Sysbench results](006-silo-sysbench.md)
- [007 — Attribution correction and mock-only validation](007-attribution-fix-mocked.md)

**Latest validation:** [57-test mock-only evidence](../results/attribution-fix-validation/README.md); next Silo/Sysbench recipe is prepared but unexecuted under `results/silo-sysbench-02/`. Earlier live optimizer histories suffered configuration attribution errors and must not be interpreted as correctly informed optimization runs.

**Latest measured results:** [Silo/Sysbench](../results/silo-sysbench-01/README.md). The completed pair did not show a stable Pareto gain. Older experiments below retain their original baseline policies.

**Current measured results:** [relationships-01 summary](../results/relationships-01/README.md). This batch has real no-cgroup A runs and 30/20 A/C sessions. The historical qualification and diagnostic figures below refer to the older pilot only.

Current status: [TESTING.md](../src/extension/TESTING.md). Data contract/commands: [EVALUATION.md](../src/extension/EVALUATION.md).

## Important protocol qualification

The newly requested A has **no dedicated workload cgroups**. Historical A used dedicated default-valued groups. There is no measured conforming A yet, and the execution path was not changed during plotting work. Old measurements are not silently relabelled.

## Four current figures

**Historical diagnostics only**, marked on every figure:

- [C improvement relative to A](../results/evaluation-redesign/historical/relative_improvement.png)
- [Stable performance summary](../results/evaluation-redesign/historical/stable_performance.png)
- [Actual applied C parameters](../results/evaluation-redesign/historical/applied_parameters.png)
- [Joint/Pareto trade-offs](../results/evaluation-redesign/historical/pareto_tradeoffs.png)
- [Optional scoped diagnostics](../results/evaluation-redesign/historical/resource_telemetry.png)

Separate [synthetic demonstration](../results/evaluation-redesign/synthetic/evaluation.md), marked synthetic and not experimental evidence. Both report sets include PNG/PDF figures, explicit source/reference metadata and CSVs. Data artifacts are copied locally from bart. This checkout tracks some historical result files; their retired images and all new outputs are visible for review without changing the existing Git ignore policy.

Old own-baseline/factor/bound-marker/A-cgroup figures are **retired** under [the historical comparison archive](../results/pilot-01/comparison/retired/). Historical CSV/JSON data remain unchanged for compatibility; use the new evaluation report, not old normalization semantics, for current analysis.
