# 007 — Attribution correction, A stable-mean bounds, five-second windows

**Mock-only task. No actual workloads, host-control writes, cgroup creation or LLM API calls.** All test execution was on bart through SSH with provider credentials removed; the final suite and explicit regression replay blocked outbound socket connections. Sources/results were synchronized with rsync.

## Root cause and correction

A read-only audit of the preceding Silo/Sysbench run found 22/30 tuning-history entries paired measurements with settings applied afterward. The final Actor blamed a 250 µs migration cost for window 30 even though that measurement used 1 ms. Raw window measurements/readbacks remain intact; previous runs are not corrected retrospectively or treated as clean optimizer evaluations.

`ScopedController` now captures its permitted settings before/after each measurement, rejects mixed windows, and puts those measured settings in `history.parameters`. Later-applied state has its own `parameters_after_window` field. Latest observations carry measured start/end configurations; prompts explicitly distinguish them from current controls and state latency/time units. Scope-private snapshots preserve independent-context privacy. The original standalone optimizer was not edited; this fixes the shared coordinated/independent extension path.

## Requested protocol

- C uses the **mean of A's complete joint stable phase**, not its initial three samples, as both default objective bounds and the report reference.
- Latency objectives have a maximum allowed latency; throughput objectives have a minimum allowed throughput.
- The loader verifies complete, untuned no-cgroup A, matching conditions/metric directions, unchanged captured host controls, positive complete stable samples and matching window/warmup durations.
- C's actual measured startup performance is no longer replaced by the external A target in the startup observation.
- Future default/example windows are **5 seconds**, preserving **30 tuning / 20 stable**. Old initial-mean proof records remain interpretable under their original policy.
- A future Silo/Sysbench recipe is prepared under `results/silo-sysbench-02/`; AST/protocol checked, never executed. Existing 8-second artifacts and historical execution recipes remain unchanged. New C requires a matching new A rather than an old eight-second reference.

## Validation

**57 extension tests passed**. The new regression exercises the real scheduler and history/prompt path with deterministic changing mocked proposals for 30/20 virtual five-second windows. It verifies measured attribution in stored history, latest/recent prompt observations and the final Actor request; distinguishes current and post-write settings; checks frozen stable state; and rejects writes within a constant window.

Negative-control replay restores the old labeling behavior only through a mock patch:

| Behavior | Misattributed tuning windows |
|---|---:|
| Legacy post-write labeling | 30/30 |
| Corrected scoped controller | **0/30** |

Both replays have 61 mocked responses and zero actual API calls. The end-to-end mocked A/C run deliberately uses different A startup and stable performance (4/100 versus 6/120), proving that stable values become C's bounds while C startup measurements remain separate. Existing privacy/failure/restoration and historical-report tests still pass.

Evidence: [validation README](../results/attribution-fix-validation/README.md), `pytest-network-blocked.log`, `pytest.xml`, `mock-attribution-summary.json`. No live post-fix performance conclusion or automatic no-regression fallback is claimed.
