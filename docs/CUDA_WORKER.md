# Focused CUDA Stratum worker

The first native worker for the Bitcoin lane is a small project-owned CUDA
executable. It reuses the verified SHA-256d computation, speaks the initial
Stratum V1 message sequence, scans nonce batches on the selected CUDA device,
submits a locally checked share, and writes an allowlisted aggregate progress
record for `ProcessWorkerAdapter`. The progress record includes the current
hash count, rate, accepted/rejected shares, best observed share difficulty,
pool-connected state, uptime, and a human-readable aggregate note.

It is separate from the manager. The manager supervises the process and the
progress cursor; the worker owns Stratum messages and the specialist
computation. That keeps the manager reusable when the first mission changes.

## Local build

The runner discovers `nvcc`, loads the Visual Studio developer environment, and
compiles for the RTX 4060's `sm_89` architecture. The executable is ignored
local runtime output:

```powershell
python scripts/run_cuda_stratum_worker.py --build
```

## Credential-free acceptance

The acceptance command starts a loopback-only mock server, launches the native
worker, and independently rebuilds the submitted header in Python. The mock
uses an intentionally easy target so a bounded test can find a share quickly:

```powershell
python scripts/run_local_cuda_worker.py
```

The expected result is one accepted share, zero rejected shares, a COMPLETE
terminal progress record, a nonzero best-share difficulty, and a note that no
pool or revenue was connected.
The mock binds to `127.0.0.1` only and uses the dummy test password
`offline-test`; it is not a pool credential.

## Manager acceptance

This command runs the same native worker through `MissionManager`, the generic
external-process adapter, the allowlisted progress parser, SQLite event ledger,
and the NVIDIA machine probe:

```powershell
python scripts/run_managed_cuda_worker.py
```

It verifies the full local path:

```text
loopback Stratum mock
        -> native CUDA worker
        -> aggregate progress JSON
        -> ProcessWorkerAdapter
        -> MissionManager
        -> SQLite events + sanitized dashboard projection
```

The manager accepts a terminal COMPLETE report even when the bounded worker
has already exited. A missing first progress file is reported as startup
pending, so initialization is not confused with a stall. The local projection
is written below ignored `runtime/`, the progress file is atomically replaced
to avoid partial JSON reads, and the run does not replace the checked-in public
preview.

## Run bounds and credentials

The worker runner defaults to one accepted share as a safe local bound. The
native executable supports `--max-shares 0` and `--seconds 0` for an unbounded
session, but that mode is not enabled by this repository and must not be
pointed at a live endpoint until the remaining endpoint, TLS, receiving, and
accounting checks are completed.

For a future local configuration, use an ignored password file with
`--password-file`; do not put a real password, token, wallet secret, seed, or
private key in this repository or in public telemetry. The current acceptance
scripts pass only the literal local test value.

## Current boundary

The worker has passed the project-owned known-vector, bounded GPU, loopback
Stratum, and manager-integration checks. It has not connected to a real pool,
created pool credit, observed a wallet, or produced revenue. A real endpoint
will be a separate, explicitly configured experiment after the worker's
network and economic reporting are reviewed.
