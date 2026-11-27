# Prepared next Silo/Sysbench experiment — NOT EXECUTED

`run_experiment.py` is a copy of the prior foreground recipe updated for the requested protocol:

- Five-second windows, **30 tuning + 20 stable**, three startup diagnostic windows.
- A captures existing settings and runs without dedicated cgroups or tuning writes.
- C uses the **arithmetic means of A's 20 stable windows** as its shared default performance bounds/reference: maximum latency / minimum throughput.
- The report uses that same verified A reference. It cannot silently substitute the initial three samples.
- A fresh default result root `results/silo-sysbench-02/run-01`; prior raw artifacts remain unchanged.
- Silo four workers at 1000 offered requests/s, scale factor 4; Sysbench CPU eight threads, prime limit 50000; no affinity partitioning. These load/thread choices were not changed by this bookkeeping task.

The script was parsed and its 5/30/20/stable_mean configuration checked without executing it. It has **not** launched workloads, created groups, changed knobs, or called an API. No new A/C results exist here. See `results/attribution-fix-validation/` for the 57 passing mock-only tests and the negative-control reproduction of the old attribution bug.

A new five-second A must be collected before the matching C can run. The archived eight-second A is not a compatible substitute. Running this recipe is a future, explicitly authorized live experiment; the current task was mock-only.
