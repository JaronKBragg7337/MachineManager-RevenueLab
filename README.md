# MachineManager Revenue Lab

MachineManager Revenue Lab is a public, evidence-first control plane for persistent AI-assisted work that can measure its own economic outcome.

The first mission is a Bitcoin proof-of-work experiment. Bitcoin is the first worker lane, not the permanent identity of the system. The same manager is intended to accept other measurable missions later: research, software, bounties, content, and other work that can produce evidence, revenue, reusable capability, or a clear reason to stop.

## What is here now

- A durable mission, worker, agent, machine-evidence, event, and treasury contract.
- A privacy-aware public snapshot format with exact, rounded, masked, and private finance views.
- An honest dashboard shell that distinguishes design-preview data from live worker evidence.
- A SQLite event-ledger boundary for local runtime history.
- A worker-adapter boundary for a future CUDA SHA-256d Stratum miner.
- Tests for event serialization and public-data sanitization.

The older Puzzle #71 MachineManager remains a separate experiment and reference implementation. This repository does not replace it or change its protected worker.

## Run the preview locally

From this directory:

```powershell
python scripts/publish_preview.py
python -m http.server 8765 --directory dashboard
```

Open `http://localhost:8765/`. The preview is deliberately marked as **DESIGN PREVIEW** and does not claim that a live mining worker or wallet is connected.

Run the standard-library test suite with:

```powershell
python -m unittest discover -s tests -v
```

## Product direction

The operating loop is:

```text
live references -> candidate missions -> workers -> evidence -> economics -> revise
```

The first financial objective is to build a transparent reserve toward a $20 monthly subscription. The dashboard will separate estimated credit, confirmed payout, money received, reserve balance, and subscription payment rather than presenting an optimistic single number.

## Public view

The dashboard is designed for a no-login public deployment. A deployment may choose whether finance is public exact, public rounded, masked, or private. A Bitcoin receiving address is treated as public proof data only when the operator explicitly enables it; private keys, seed phrases, extended private keys, credentials, and tokens are not part of the public contract.

The public deployment URL will be added after the new GitHub repository and Pages destination are selected. Until then, this local preview is the source of truth for the UI build.

## Build documents

- [Project brief](docs/PROJECT_BRIEF.md) — the durable intent and decisions from the design conversation.
- [Architecture](docs/ARCHITECTURE.md) — the interchangeable mission and evidence model.
- [Build state](docs/BUILD_STATE.md) — the checkpoint that survives context compaction.

