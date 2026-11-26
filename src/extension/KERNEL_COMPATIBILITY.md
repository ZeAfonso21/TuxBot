# Eight-parameter compatibility review

The initial review below was source/read-only inspection, not empirical validation. The target is now identified as **bart, Linux 5.15.0-89-lowlatency**; see TESTING.md for subsequent authorized remote checks. Real cgroup CPU writes/readback/restoration and, subsequently, the six CPU-related scalar host controls were exercised in the real Sysbench C pilot. Busy polling was intentionally not exposed for these workloads; cstate_max remains excluded. Runtime host-control availability must still be resolved per run rather than assumed from either machine.

| Logical name | Linux 5.15 / existing implementation interface | Semantics and scope | Extension policy / constraints |
|---|---|---|---|
| `min_granularity_ns` | `/sys/kernel/debug/sched/min_granularity_ns`; older sysctl `/proc/sys/kernel/sched_min_granularity_ns` | CFS scheduling granularity, shared scheduler policy; ns | Existing identical-name interfaces only; integer 100,000–100,000,000 |
| `latency_ns` | `/sys/kernel/debug/sched/latency_ns`; older `/proc/sys/kernel/sched_latency_ns` | CFS target scheduling period, not an application latency guarantee; ns | Existing identical-name interfaces only; 1,000,000–1,000,000,000 |
| `wakeup_granularity_ns` | `/sys/kernel/debug/sched/wakeup_granularity_ns`; older `/proc/sys/kernel/sched_wakeup_granularity_ns` | CFS wakeup preemption granularity; ns | Existing identical-name interfaces only; 0–100,000,000 |
| `migration_cost_ns` | `/sys/kernel/debug/sched/migration_cost_ns`; older `/proc/sys/kernel/sched_migration_cost_ns` | Scheduler cache-hot migration heuristic, not a CPU affinity control; ns | Existing identical-name interfaces only; 0–100,000,000 |
| `cstate_max` | Existing `set_cstate_max` translates logical state names into `/sys/devices/system/cpu/cpu*/cpuidle/state*/disable` masks | Actually per-CPU/per-idle-state. Driver parameters `/sys/module/intel_idle/parameters/max_cstate` and `/sys/module/processor/parameters/max_cstate` are different interfaces, often boot/module-time constraints | **Excluded**: no verified reversible scalar mapping. State indices, names, and exit latencies differ across drivers; a name-based C6 mask is not automatically equivalent to a driver maximum |
| `napi_busy_poll` | Existing implementation aliases this logical name to `/proc/sys/net/core/busy_poll` (`net.core.busy_poll`) | Busy-poll budget in microseconds for eligible sockets; network-namespace-wide, shared by both applications in the runner's namespace | Integer 0–1000; no IRQ-affinity changes; no invented `/proc/sys/.../napi_busy_poll` path |
| `min_perf_pct` | `/sys/devices/system/cpu/intel_pstate/min_perf_pct` | Intel P-state driver-wide minimum percentage, not per-cgroup or truly per-core | Integer 0–100; requires readable/writable paired max endpoint; min ≤ max |
| `max_perf_pct` | `/sys/devices/system/cpu/intel_pstate/max_perf_pct` | Intel P-state driver-wide maximum percentage; availability depends on hardware and driver mode | Integer 1–100; requires paired min endpoint; min ≤ max; dependency-aware writes and restore |

Ranges are conservative experiment policy, **not a claim that every value is universally safe**. Kernel constraints and permissions still apply; failed writes/readbacks trigger rollback. Initial values outside tuning ranges can still be restored exactly. CPU hotplug, driver reload, namespace changes, and externally concurrent kernel writes are outside the supported experiment contract.

## EEVDF

EEVDF kernels changed the CFS slice-selection interfaces. `base_slice_ns` is **not substituted** for `min_granularity_ns`, `latency_ns`, or `wakeup_granularity_ns`: the semantics are not interchangeable. Neither similarly named controls nor a presumed kernel-version cutoff establishes equivalence. Removed or inaccessible interfaces are excluded. No verified semantic replacement is currently implemented.

The old sysctl and debugfs paths above are alternate historical locations for the same named controls, not EEVDF replacements. The runner never mounts debugfs or invokes sudo. An administrator must separately provision any required debugfs access on the experimental host.

## Read-only development-host observations

`/proc/sys/kernel/osrelease`: **7.3.4-arch1-2**.

- The four named scheduler debugfs and sysctl files were not accessible/present from this session. This does **not** distinguish removal from an unmounted/inaccessible debugfs.
- `/proc/sys/net/core/busy_poll` was readable, value `0`.
- Intel P-state percentage endpoints were readable, values `9` and `100`.
- Intel idle `max_cstate` was read-only, value `9`; the processor driver's parameter was listed root-readable only.
- No idle-state masks were changed or investigated by writing. No writable capability has been empirically established.

Thus the only locally observed scalar candidates are busy polling and the two Intel P-state percentages. They are not automatically the active set on the future experimental machine.

## Subsequent target observations: bart

Read-only resolution during the authorized cgroup smoke check found all seven scalar candidates accessible and reported writable: the four exact-name scheduler debugfs interfaces, `/proc/sys/net/core/busy_poll`, and the paired Intel P-state percentage files. Values were min granularity 3000000, scheduler latency 24000000, wakeup granularity 4000000, migration cost 500000, busy_poll 0, minimum percentage 45 and maximum 100. The full report is in `results/cgroup-smoke/stdout.json`. These are candidate availability observations, **not** write validation or a default-state attestation. `cstate_max` remains excluded. No replacement aliases were required on this target.

## Subsequent live validation: Sysbench C pilot

The four scheduler controls and both Intel P-state percentage endpoints were written/read back successfully through the scoped actuator on bart, with the original selected snapshot restored after completion. The pilot narrowed scheduler latency to 6–48 ms, min granularity to 0.5–6 ms, wakeup granularity to 0–8 ms, migration cost to 0–2 ms, min_perf_pct to 45–100 and max_perf_pct to 80–100. These limits may only narrow the verified schema, never add interfaces. See `results/pilot-01/C-coordinated/results.json`, sibling delegation evidence and `progress/002-sysbench-pilot.md`.

This validates successful writes and final restoration for the actual sampled values on this Linux 5.15 target. It does not validate every allowed value, all failed-partial-write paths, newer-kernel compatibility or equivalence of unimplemented EEVDF controls. Busy-poll writes and idle-state masks were not tested.

## Runtime evidence

`host.py` retains logical name, fixed candidate interfaces, integer constraints, host scope, approval, availability, initial value, and access status separately. `host_compatibility.json` records the resolved interface on the experimental machine. The active LLM schema includes only approved, readable, writable candidates. Unsupported controls are absent, never silently emulated. Coordinated execution refuses to proceed if the active host set is empty.

Useful references for future machine validation: Linux `Documentation/admin-guide/cgroup-v2.rst`, `Documentation/admin-guide/pm/intel_pstate.rst`, `Documentation/admin-guide/pm/cpuidle.rst`, `Documentation/admin-guide/sysctl/net.rst`, and `Documentation/scheduler/sched-eevdf.rst` from the **actual target kernel tree**. Confirm target-specific constraints before authorizing experiments.
