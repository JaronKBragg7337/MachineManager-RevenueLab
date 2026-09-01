# Manager runtime

The reusable manager is in `revenue_lab/manager.py`. It is deliberately
mission-neutral: the manager coordinates a worker adapter, while the adapter
owns the specialist computation.

## Evidence rule

The manager requires more than a process that is still alive. A useful worker
observation includes a fresh aggregate progress cursor. A live process whose
cursor does not advance becomes a stall after the configured number of
observations. Missing or malformed progress is therefore visible instead of
being silently treated as success.

Each cycle can create:

- a work packet;
- a health or progress event;
- a state transition when the mission changes;
- a public sanitized projection; and
- a durable SQLite event entry.

The event ledger retains the local history. The dashboard projection contains
only the compact public view and never includes a launch command, local path,
process ID, credential, or raw model response.

## Bounded recovery

`ManagerPolicy` controls two important testable behaviors:

- `stall_after_observations`: how many non-advancing observations are tolerated;
- `max_recoveries`: how many worker recovery attempts are allowed before the
  mission becomes `ESCALATED`.

The manager records `STALLED` or `FAILED`, `RETRYING`, recovery, and
`ESCALATED` transitions. It does not restart a repeatedly failing worker
forever.

Run all deterministic scenarios locally:

```powershell
python scripts/run_reliability_scenarios.py
```

The report and per-scenario projections are written under the ignored
`runtime/` directory. The scenarios are intentionally not Bitcoin mining and
do not use the GPU, pool, wallet, or external accounts.

## Future live lane

The first live adapter can implement the existing `WorkerAdapter` protocol and
provide a progress report with aggregate metrics such as hashrate, accepted
shares, rejected shares, best share difficulty, pool connection, and uptime.
The real worker and pool must be selected and configured separately; this
runtime does not invent a binary, launch arguments, pool endpoint, or wallet
destination.
