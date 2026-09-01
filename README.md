# MachineManager Revenue Lab

MachineManager Revenue Lab is a public, evidence-first control plane for persistent AI-assisted work that can measure its own economic outcome.

The first mission is a Bitcoin proof-of-work experiment. Bitcoin is the first worker lane, not the permanent identity of the system. The same manager is intended to accept other measurable missions later: research, software, bounties, content, and other work that can produce evidence, revenue, reusable capability, or a clear reason to stop.

## What is here now

- A durable mission, worker, agent, machine-evidence, event, and treasury contract.
- A privacy-aware public snapshot format with exact, rounded, masked, and private finance views.
- An honest dashboard shell that distinguishes design-preview data from live worker evidence.
- A SQLite event-ledger boundary for local runtime history.
- A worker-adapter boundary for a future CUDA SHA-256d Stratum miner.
- An offline Stratum contract for validating jobs, building headers, checking
  targets, and constructing submit parameters without contacting a pool.
- A loopback-only mock Stratum server that independently verifies submitted
  shares before any real endpoint is considered.
- A credential-free CUDA SHA-256d benchmark that verifies the Bitcoin genesis
  header before measuring bounded RTX 4060 work.
- A reusable manager loop that distinguishes fresh progress from process liveness,
  recovers bounded failures, and escalates repeated failures.
- Deterministic crash, stall, false-liveness, and repeated-failure scenarios.
- Tests for event serialization, manager recovery, and public-data sanitization.

The older Puzzle #71 MachineManager remains a separate experiment and reference implementation. This repository does not replace it or change its protected worker.

## Run the preview locally

From this directory:

```powershell
python scripts/publish_preview.py
python -m http.server 8765 --directory dashboard
```

Open `http://localhost:8765/`. The preview is deliberately marked as **DESIGN PREVIEW** and does not claim that a live mining worker or wallet is connected.

To exercise the continuous evidence path with a deterministic worker, run this in a second terminal:

```powershell
python scripts/run_demo_runtime.py --iterations 20 --interval 2
```

The page will show real synthetic packets and state changes as they are published. It remains marked **SYNTHETIC DEMO**; these packets are runtime evidence tests, not Bitcoin work or revenue.

Exercise the manager's bounded recovery behavior without using the GPU or any
external service:

```powershell
python scripts/run_reliability_scenarios.py
```

The command writes an ignored local report under `runtime/` and runs five
scenarios: healthy progress, a one-time crash, a one-time stall, a process-only
false-liveness signal, and a repeated failure that must escalate.

Verify and measure the local Bitcoin SHA-256d kernel without a pool, wallet, or
network connection:

```powershell
python scripts/run_cuda_benchmark.py --hashes 5000000
```

The benchmark checks the Bitcoin genesis-header digest first and reports a raw
local GPU rate only when that check passes. It does not claim mining revenue;
see [the benchmark contract](docs/CUDA_BENCHMARK.md).

Run the reusable manager as a local service (still synthetic until the live
worker adapter is selected):

```powershell
python scripts/run_managed_runtime.py --iterations 20 --interval 2
```

Leaving out `--iterations` keeps the manager running continuously. Its default
JSON projection and SQLite ledger live under the ignored `runtime/` directory.

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

Public links:

- [Mission Control dashboard](https://jaronkbragg7337.github.io/MachineManager-RevenueLab/)
- [Source repository](https://github.com/JaronKBragg7337/MachineManager-RevenueLab)

The dashboard is currently an honest design preview while the live worker adapter is being selected and benchmarked.

## Build documents

- [Project brief](docs/PROJECT_BRIEF.md) — the durable intent and decisions from the design conversation.
- [Architecture](docs/ARCHITECTURE.md) — the interchangeable mission and evidence model.
- [Manager runtime](docs/MANAGER_RUNTIME.md) — progress evidence, bounded recovery, and reliability scenarios.
- [CUDA benchmark](docs/CUDA_BENCHMARK.md) — the local known-vector and throughput check.
- [Worker selection](docs/WORKER_SELECTION.md) — candidate audit and gates before pool connection.
- [GBXminer build audit](docs/GBXMINER_BUILD.md) — why the first third-party candidate remains reference-only.
- [Offline Stratum contract](docs/STRATUM_CONTRACT.md) — protocol and Bitcoin header/share math with no network access.
- [Build state](docs/BUILD_STATE.md) — the checkpoint that survives context compaction.
- [Deployment](docs/DEPLOYMENT.md) — how the public no-login dashboard is served.
