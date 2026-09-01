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

Run the reusable manager itself with a bounded synthetic service:

```powershell
python scripts/run_managed_runtime.py --iterations 20 --interval 2
```

For a continuous local service, leave out `--iterations` (it defaults to zero):

```powershell
python scripts/run_managed_runtime.py --interval 15
```

The default projection is kept under ignored `runtime/managed-dashboard/` so a
local demo cannot silently replace the checked-in public preview. To serve the
managed projection locally, point `--dashboard-data` at a directory served by
an HTTP server. The service still uses only the deterministic synthetic worker
until a real adapter is explicitly configured.

## Future live lane

The first live adapter can implement the existing `WorkerAdapter` protocol and
provide a progress report with aggregate metrics such as hashrate, accepted
shares, rejected shares, best share difficulty, pool connection, and uptime.
The real worker and pool must be selected and configured separately; this
runtime does not invent a binary, launch arguments, pool endpoint, or wallet
destination.
