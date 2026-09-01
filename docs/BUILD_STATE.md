# Build state

Last checkpoint: 2026-09-01

## Current checkpoint

- New repository: `machine-manager-revenue-lab` under the Codex Active projects workspace.
- Status: foundation, reusable manager runtime, and local CUDA proof-of-work benchmark are complete; live pool integration remains pending.
- The legacy Puzzle #71 MachineManager remains a separate reference and is not being modified by this project.
- No live Bitcoin mining worker has been connected here yet.
- No wallet address, private key, seed, credential, token, pool secret, or raw machine log has been added here.
- The dashboard will begin in an explicit design-preview mode and will not claim live mining evidence.

## Completed in this checkpoint

- Durable project brief created from the owner’s design conversation.
- Interchangeable mission/evidence/economics architecture recorded.
- Public finance visibility modes recorded.
- Compaction-resistant build state created.
- Standard-library contracts, SQLite event ledger, preview publisher, and first dashboard shell implemented.
- Local preview verified through the browser at `http://127.0.0.1:8765/` with working navigation and refresh.
- A bounded synthetic runtime now publishes real work packets and manager state changes into the same SQLite/public projection path.
- NVIDIA machine-probe parsing and an allowlisted worker-progress parser are now implemented.
- A generic external-process adapter now separates launch/liveness from useful-progress evidence.
- A reusable mission manager now records every observation, detects false liveness and stalls, performs bounded recovery, and escalates repeated failure.
- Deterministic reliability workers and a local scenario runner cover healthy progress, crash, stall, false liveness, and repeated failure.
- A local managed-runtime entry point can run bounded or continuous synthetic service cycles while keeping the checked-in public preview untouched by default.
- A credential-free CUDA SHA-256d benchmark now verifies the Bitcoin genesis
  header before timing deterministic RTX 4060 work. A bounded 5,000,000-hash
  run passed the known vector and measured approximately 747 million hashes per
  second locally; it contacted no network and made no revenue claim.
- An offline Stratum contract now validates `mining.notify` fields, builds
  coinbase/merkle/header data, decodes compact targets, checks digest ordering,
  and constructs submit parameters. It is transport-free: no pool has been
  contacted and no revenue has been claimed.
- A loopback-only mock Stratum server now passes the subscribe, authorize,
  notify, independent header reconstruction, target comparison, and submit
  sequence. It binds only to localhost during tests and uses no credentials.
- GBXminer `develop` is recorded as the provisional Stratum worker candidate;
  its source has a CUDA SHA-256d path, Stratum/GBT plumbing, and monitoring API,
  but its checked-in Visual Studio project still imports CUDA 9.0 settings and
  has not passed a native build on this machine. No live worker is attached.
- Twenty-two core tests plus the public-data validator are passing.

## Next implementation checkpoint

1. Connect a pinned worker implementation to the local mock and verify its
   progress report against the allowlisted manager contract.
2. Select and document the first Stratum worker implementation without
   committing credentials.
3. Connect pool-job observations to the worker contract and economics ledger.
4. Review the Live Reference Principle source before finalizing reference
   ingestion.

## Public handoff status

The public repository is [MachineManager-RevenueLab](https://github.com/JaronKBragg7337/MachineManager-RevenueLab). Pages is configured for the `main` branch root and forwards to [Mission Control](https://jaronkbragg7337.github.io/MachineManager-RevenueLab/dashboard/). The branch-source deployment is verified: the remote page loads without login, the root redirects, and the dashboard renders its preview data.

The manager runtime and reliability scenario runner are local-only build
artifacts at this checkpoint. They do not connect a Bitcoin worker, pool,
wallet, or live revenue source.
