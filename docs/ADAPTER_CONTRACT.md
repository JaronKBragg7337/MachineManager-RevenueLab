# Worker adapter contract

The new manager is not going to treat a mining executable as the architecture. It will treat it as one implementation of a worker adapter.

## First adapter

`bitcoin-sha256d-stratum` is the first planned adapter. It must prove the actual Bitcoin work loop through observable facts:

```text
pool job -> header construction -> SHA-256d attempts -> target comparison -> share submission
```

The public projection should expose aggregate work and outcome signals, not a stream of pretend reasoning:

- current connection state;
- hashrate and runtime;
- accepted/rejected shares;
- best share difficulty;
- pool/job freshness;
- machine activity and power evidence;
- payout estimate, confirmed credit, and receipt status.

The adapter may write a small progress JSON report. The manager reads only the allowlisted aggregate fields in `revenue_lab/progress.py`; unknown fields are ignored and malformed reports fail closed.

## Lifecycle

Every adapter implements:

```text
start(objective, resources) -> running handle
observe() -> WorkerObservation
stop(reason) -> outcome
recover(reason) -> outcome
```

The manager combines process state, fresh progress, and resource evidence before declaring useful work. A live process with no advancing work is not healthy.

`ProcessWorkerAdapter` supplies the generic external-process boundary. It launches only the configured command vector, keeps stdout/stderr out of the public projection, and reports `process_only` when no aggregate progress file is available. That state is intentionally insufficient for a healthy-work claim.

## Implementation sequence

1. Select and document a worker implementation and pool lane.
2. Benchmark it independently with no credentials committed.
3. Emit a small structured progress record using the adapter contract.
4. Run healthy, crash, stalled, restart, and malformed-observation tests using a synthetic worker first.
5. Connect the real adapter and compare its observed evidence to the synthetic contract.
6. Only then enable unattended operation and public economic reconciliation.

This keeps the control plane reusable and makes it possible to switch from pool mining to another mission without rewriting the dashboard.
