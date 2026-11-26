# First authorized remote validation on bart

This supersedes the implementation-only testing status in the original handoff. **All execution occurred through `ssh bart 'COMMAND'`. Nothing was executed or tuned locally.** Source edits were made through the SSHFS mount of `/work_dir`.

## Environment and credentials

- Hostname verified as `bart` before installation/system modifications.
- Kernel: `5.15.0-89-lowlatency`; Python 3.10.12.
- Isolated environment: `/work_dir/tuxbot-venv`; installed google-genai, pytest and matplotlib with their dependencies. No system Python packages were installed. Exact versions: `results/extension-validation/installed-packages.txt`.
- User-supplied Gemini credential stored outside the repository in `/work_dir/.secrets/gemini.env` (directory mode 0700, file mode 0600). Load it into a remote shell using `. /work_dir/.secrets/gemini.env`. The value was never displayed or written into source/configuration/test reports. No SSH keys or passphrases were accessed.
- Copied repository ownership triggered Git's dubious-ownership protection. No global Git trust exception was installed. The existing supported environment override `OS_PARAM_TUNING_ROOT=/work_dir/TuxBot` bypasses Git-dependent repository-root discovery for tests/benchmarks.

## Results

**16 tests passed** in the final remote pytest invocation:

```sh
ssh bart 'cd /work_dir/TuxBot && OS_PARAM_TUNING_ROOT=/work_dir/TuxBot MPLBACKEND=Agg PYTHONPATH=src /work_dir/tuxbot-venv/bin/python -m pytest -q src/extension/test_extension.py src/extension/test_controller.py src/extension/test_runner.py tests/test_perf_collection.py'
```

Artifacts: `results/extension-validation/pytest.log`, `pytest.xml`, and `installed-packages.txt`. Extension compilation/imports also passed remotely.

Coverage includes:

- Baseline median, direction-specific improvement, user bounds versus noise-tolerant default regressions; invalid/missing measurements.
- Scoped type/range checks, duplicate JSON keys, quotas, P-state dependency, readback, exact restore and failed-partial-write rollback using temporary files.
- Shared-window rendezvous and independent projection privacy.
- Actual original dual-loop scheduling/final-freeze/history persistence in coordinated and two-independent modes, with fake collectors/providers/controls.
- Measurement failure aborting both independent controllers.
- Persistence failure cannot report a completed run.
- Full A/B/C runner lifecycle, baseline capture, restoration, JSON export, CSV summaries and plots, with fake workloads/interfaces/providers. Mock data are not experiment results.
- Existing three perf-parser tests with toy data/mocked processes, not hardware-counter validation.

Early runs exposed test-fixture mistakes (history directories colliding with temporary control files; missing fake cgroup.procs). Those fixtures were corrected. Two original perf tests initially failed due to Git root discovery; they passed with `OS_PARAM_TUNING_ROOT`. These early failures are not omitted from this account.

## Live API smoke checks

There were **four generation attempts** and one authenticated model-list request, not a tuning session:

1. HTTP 400: Gemini rejected `additional_properties` in the generated schema.
2. After removing unsupported provider-schema fields, HTTP 404: `gemini-2.5-flash-lite` is unavailable to new users. The model list still includes it, so listing alone does not prove usability.
3. Coordinated schema on `gemini-3.5-flash-lite`: validated; empty updates; **no actuation**; 155 input + 34 output = 189 reported billable tokens, about 0.935 s.
4. Independent schema on the same model: validated; empty updates; **no actuation**; 131 input + 40 output = 171 reported billable tokens, about 0.796 s.

Successful generations total **360 reported billable tokens**. No euro charge or remaining account balance was independently verified; the supplied €10 budget was not deliberately spent down. Requests were capped at 256 output tokens and 30 seconds, with no automatic smoke-test retries. No further live API calls were made.

Fixes: remove `additionalProperties` from the Gemini response schema, retain strict Python-side rejection of unknown fields, and use `gemini-3.5-flash`/`gemini-3.5-flash-lite` as extension-runner/example defaults. Only the Lite model was actually generated against; the Actor model still needs a live end-to-end check. Original frozen TuxBot model definitions were not changed.

`api_smoke.py` is an explicitly gated helper that uses temporary control files and never applies proposals. It supports `--independent` and `--model`.

## Live cgroup lifecycle smoke check

The first attempt correctly refused to run because CPU delegation was unavailable to the child subtree. It cleaned up its empty test group without errors.

The machine root initially had `memory pids` in `cgroup.subtree_control`. For a second isolated smoke check, CPU delegation was temporarily enabled, and was **restored to exactly `memory pids` afterward**. The pre-change state was persisted before modification.

Verified on fresh disposable groups:

- `cpu.weight`: A = 200, B = 300, exact readback.
- `cpu.max`: A = `50000 100000`, exact readback.
- Both the launcher and its short-lived child had membership in the A cgroup before executing their probe.
- An A-only actuator rejected B updates and host updates.
- Original control snapshots restored; no workload benchmark ran.
- Test groups removed; cleanup and parent-controller restoration reported no errors.

Artifacts: `results/cgroup-smoke/stdout.json`, `stderr.log`, and `parent_state.json`. `cgroup_smoke.py` does not enable ancestor controllers itself: it requires preprovisioned CPU delegation and refuses the wrong hostname by default.

No scheduler, frequency, network, memory, or other host tunable was written. Only temporary cgroup controller delegation and disposable cgroup CPU settings were modified. Global host actuation/rollback remains untested against real kernel tunables.

## Target interface observations

All seven scalar candidates were readable and reported writable on bart:

- `min_granularity_ns`: 3000000
- `latency_ns`: 24000000
- `wakeup_granularity_ns`: 4000000
- `migration_cost_ns`: 500000
- `napi_busy_poll` / `net.core.busy_poll`: 0
- Intel P-state minimum: 45; maximum: 100

The scheduler candidates resolve to the existing debugfs paths. These observations do not attest that the entire machine is at factory/default settings. `defaults_verified` remains false in the checked-in experiment examples. `cstate_max` remains excluded for the reasons in `KERNEL_COMPATIBILITY.md`.

## Still unverified / next stage

- Real supported-workload A/B/C experiments, application CSV timestamp conventions, saturation/load calibration and stable-phase performance. Dependency submodule directories remain empty; no TailBench sources/data were downloaded or compiled.
- Hardware perf collection: no `perf` executable was found during preflight; the safe parser tests do not replace installing/verifying the matching tool.
- Real host-kernel writes, kernel rollback failure recovery, memory.high under a real application, and process/signal cleanup under a live full tuning run.
- Actual multi-window model-driven tuning and the Actor model. Both live API checks were single no-op proposals on temporary controls, not full controller sessions.
- Real monetary usage/account balance.

Further work should provision dependencies and an explicitly delegated experiment root, then perform a short, separately budgeted integration run. Do not interpret mocked performance data, smoke checks, or passing unit tests as research evidence that coordinated tuning improves performance.

Test helpers and fixes were initially made in the remote `/work_dir/TuxBot` copy, then synchronized back into the local checkout with rsync. **The local checkout is the source of truth.** Future source changes must be kept synchronized with the remote runtime copy. Git metadata, credentials, caches and result artifacts are excluded from source synchronization; newer local files are preserved. All tests and workloads still execute remotely only.
