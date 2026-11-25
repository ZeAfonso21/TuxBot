# Eight-parameter compatibility review

This is a **source/interface review, not empirical validation**. No writes, mounts, experiments, or privileged probes were performed. The dedicated experimental kernel has not been identified. Runtime availability is therefore established again by the authorized runner, not assumed from this development machine.

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

## Runtime evidence

`host.py` retains logical name, fixed candidate interfaces, integer constraints, host scope, approval, availability, initial value, and access status separately. `host_compatibility.json` records the resolved interface on the experimental machine. The active LLM schema includes only approved, readable, writable candidates. Unsupported controls are absent, never silently emulated. Coordinated execution refuses to proceed if the active host set is empty.

Useful references for future machine validation: Linux `Documentation/admin-guide/cgroup-v2.rst`, `Documentation/admin-guide/pm/intel_pstate.rst`, `Documentation/admin-guide/pm/cpuidle.rst`, `Documentation/admin-guide/sysctl/net.rst`, and `Documentation/scheduler/sched-eevdf.rst` from the **actual target kernel tree**. Confirm target-specific constraints before authorizing experiments.
