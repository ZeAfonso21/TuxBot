# Mock-only attribution/baseline regression validation

No actual workload or LLM API was executed. All Python execution ran on bart via SSH. No credential file was sourced; real provider keys were removed from the test environment. Native workload launchers/collectors and Gemini clients/transport are mocked. Controls are temporary ordinary files, not sysfs/cgroups. Outbound socket connections were blocked for the final suite and explicit negative-control replay.

## Results

- **57 tests passed** in the final network-blocked extension suite: `pytest-network-blocked.log`, `pytest.xml`.
- `mock-attribution-summary.json` is explicitly **synthetic**. It replays the real scheduler with 30 tuning / 20 stable virtual five-second windows and changing mocked suggestions:
  - Legacy post-write labeling: **30/30 tuning windows misattributed**.
  - Corrected scoped controller: **0/30 misattributed**.
  - Each replay uses 61 mocked provider responses; **zero API calls**.
- Tests verify stored measurements, recent-history prompts, the latest-observation prompt, the final Actor request after window 30, and frozen stable snapshots.
- A separate test rejects controls changing inside a supposedly constant measurement window.
- Existing independent-context privacy tests still pass with the new measured-configuration fields.

## Corrected semantics

The scoped controller snapshots its permitted controls immediately before and after measurement. It rejects mixed windows. `history.parameters` identifies the measured configuration, while `history.parameters_after_window` separately identifies newer proposals committed after the measurement. The current live `controls` field remains distinct. Deep copies prevent later writes from altering historical attribution. Prompt instructions state that distinction and clarify the supported latency/event/time units.

C's default shared reference is now the **arithmetic mean of the complete recorded A stable phase**. Default Silo latency is an upper allowed bound; default Sysbench throughput is a lower allowed bound. C's measured startup performance is kept separate from those bounds. The synthetic integration test deliberately gives A initial values 4/100 and A stable values 6/120, then confirms C receives the latter targets but retains its measured startup values 4/100.

References require completed untuned no-cgroup A, matching workloads/objectives, unchanged captured host settings, complete positive joint stable samples and matching window/warmup durations. An old eight-second A cannot be silently used for a new five-second C. Historical initial-mean proofs remain recognized without rewriting their policy.

## Scope

Future runner defaults/example profiles use **5 seconds, 30 tuning / 20 stable**. The next Silo/Sysbench recipe is prepared under `results/silo-sysbench-02/` and was AST/syntax/protocol checked **without execution**. No prior measurement or report was regenerated or relabelled. No improvement guarantee or automatic performance fallback was added. The attribution correction is in the extension's scoped controller, shared by coordinated and independent modes; the original standalone optimizer was not modified.

This validates bookkeeping and protocol handling, not real performance after the fix. A new live A/C experiment is still required when authorized.
