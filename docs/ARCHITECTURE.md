# Architecture

## North-star flow

```text
live references
      |
      v
mission registry -----> objective + success measures
      |
      v
manager -------------> agent roster -------------> specialist worker
      |                       |                           |
      +-----------------------+---------------------------+
                              |
                              v
                        evidence ledger
                              |
                 +------------+-------------+
                 v                          v
          public snapshot                economics
                 |                          |
                 +------------+-------------+
                              v
                       dashboard + review
```

## Layer ownership

### Reference layer

Stores live facts that affect decisions: pool terms, current difficulty, software capabilities, provider behavior, and mission assumptions. Every reference needs a source, observed timestamp, and review/expiry timestamp. A reference is not silently promoted to a timeless rule.

### Mission layer

Describes the objective independently of its worker implementation. A mission has an outcome, a target, a lane, a lifecycle state, and an evidence policy. The initial mission is Bitcoin mining, but the contract does not mention KeyHunt.

### Manager layer

Owns scheduling, state transitions, liveness checks, bounded recovery, escalation, adoption after restart, and publication cadence. The manager does not pretend that process-alive means useful work; worker progress and machine evidence are separate signals.

### Agent layer

Represents AI reasoning and coordination. Agents publish bounded work packets: a question, an observation, a decision, a test, a proposal, or a review. Agent text is evidence only when linked to a real input, output, and event timestamp.

### Worker layer

Implements a specialist task. Each adapter exposes a common contract:

```text
start(objective, resources) -> worker handle
observe() -> worker snapshot
stop(reason) -> outcome
recover(reason) -> outcome
```

The first adapter will be a CUDA SHA-256d Stratum worker. Future adapters can cover research crawlers, build/test jobs, or other measurable work without changing the public dashboard contract.

### Evidence layer

Uses an append-only local SQLite ledger for complete runtime events. A publisher turns an allowlisted subset into compact public JSON. Public data is a projection, not a copy of raw logs.

### Economics layer

Separates:

```text
estimated credit -> confirmed payout -> money received -> reserve -> subscription paid
```

This prevents a projected mining result from being shown as cash. Shared electricity is represented with a quality label such as `unknown_shared_bill` or `machine_estimate`.

### Presentation layer

The dashboard renders the same structured snapshot as a website, a mobile view, and eventually a visual/3D scene. The scene can animate transitions and topology, but it consumes events; it does not invent them.

## Public finance modes

| Mode | Amounts | Receiving address | Intended use |
| --- | --- | --- | --- |
| `public_exact` | Exact | Visible | Proof-of-concept deployment using a dedicated receiving address |
| `public_rounded` | Rounded | Masked | Public progress without exact balance history |
| `masked` | Hidden/qualitative | Masked | Public activity with private financial figures |
| `private` | Omitted | Omitted | Local-only finance |

The runtime may hold a public receiving address, but no private wallet material is part of the contract.

## State model

```text
PLANNED -> QUEUED -> STARTING -> RUNNING -> VERIFYING -> COMPLETE
                       |             |          |
                       v             v          v
                    FAILED        STALLED    RETRYING
                       |                         |
                       +-------> ESCALATED <----+

CANCELLED is a terminal operator/objective state.
```

## Failure philosophy

The manager should recover from an observed failure that it has authority and tooling to handle. It should escalate when an external authority, identity step, ambiguous objective, or untested capability is genuinely required. Model/provider behavior is measured during onboarding rather than copied into every mission as a speculative restriction.

