# Build state

Last checkpoint: 2026-09-01

## Current checkpoint

- New repository: `machine-manager-revenue-lab` under the Codex Active projects workspace.
- Status: initial foundation build in progress.
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
- Seventeen core tests plus the public-data validator are passing.

## Next implementation checkpoint

1. Add the real manager runtime and synthetic worker scenarios.
2. Choose and benchmark a SHA-256d worker without committing credentials.
3. Connect pool observations to the worker contract and economics ledger.
4. Review the Live Reference Principle source before finalizing reference ingestion.

## Public handoff status

The public repository is [MachineManager-RevenueLab](https://github.com/JaronKBragg7337/MachineManager-RevenueLab). Pages is configured for the `main` branch root and forwards to [Mission Control](https://jaronkbragg7337.github.io/MachineManager-RevenueLab/dashboard/). The branch-source deployment is verified: the remote page loads without login, the root redirects, and the dashboard renders its preview data.
