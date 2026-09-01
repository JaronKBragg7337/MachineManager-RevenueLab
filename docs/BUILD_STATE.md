# Build state

Last checkpoint: 2026-09-01

## Current checkpoint

- New repository: `machine-manager-revenue-lab` under the Codex Active projects workspace.
- Status: foundation and reusable manager runtime build in progress.
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
- Twenty-two core tests plus the public-data validator are passing.

## Next implementation checkpoint

1. Add a real manager service entry point and synthetic worker scenarios.
2. Choose and benchmark a SHA-256d worker without committing credentials.
3. Connect pool observations to the worker contract and economics ledger.
4. Review the Live Reference Principle source before finalizing reference ingestion.

## Public handoff status

The public repository is [MachineManager-RevenueLab](https://github.com/JaronKBragg7337/MachineManager-RevenueLab). Pages is configured for the `main` branch root and forwards to [Mission Control](https://jaronkbragg7337.github.io/MachineManager-RevenueLab/dashboard/). The branch-source deployment is verified: the remote page loads without login, the root redirects, and the dashboard renders its preview data.

The manager runtime and reliability scenario runner are local-only build
artifacts at this checkpoint. They do not connect a Bitcoin worker, pool,
wallet, or live revenue source.
