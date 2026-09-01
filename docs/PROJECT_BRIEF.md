# Project brief

## Purpose

Build a persistent machine-resident work system that lets AI agents and specialist workers continue useful work without requiring a person to manually restart every step. The system should make the work visible, measurable, and honest enough that another person can understand what happened from the public evidence trail.

The first mission is an actual Bitcoin mining experiment with a measurable path from computation to pool credit and, if it occurs, money received. The system must remain interchangeable so the Bitcoin lane can later be paused, replaced, or joined by research, software, media, bounty, or other revenue-producing missions.

## Current decisions

1. Keep the old Puzzle #71 MachineManager as its own experiment and reference implementation.
2. Build this as a clean repository with a new visual identity and a new mission model.
3. Reuse proven operational ideas from the old system: durable events, worker health, recovery, SQLite state, sanitized publishing, and public evidence.
4. Do not hard-code the new system around KeyHunt, Puzzle #71, or one vendor/model.
5. Show actual work packets and outcomes. Decorative animation may explain the system, but it must never be presented as live work unless it is backed by an event or telemetry record.
6. Treat the $20 monthly subscription as the first economic milestone. Raise the target only after the system reaches it with confirmed evidence.
7. Electricity is shared with other machine use, so the first version will label machine-attributed cost as estimated or unknown instead of inventing a precise bill allocation.
8. Support four finance visibility modes: public exact, public rounded, masked, and private.
9. A public Bitcoin receiving address may be shown when explicitly enabled. It is proof-of-receiving information, not a credential. Wallet secrets never belong in the repository, runtime event stream, or public snapshot.
10. An unexpected payment is an observable event to investigate and document. A return payment is a separate, deliberate transaction and must not be described as an automatic refund.
11. Policy should follow evidence. A capability is recorded as observed, tested, or unknown; restrictions are not duplicated merely because a model/provider may already enforce them.
12. Live external facts use a source, timestamp, and expiry/review date so old assumptions do not quietly become permanent architecture.

## What success looks like

Someone viewing the public page can answer:

- What mission is active?
- Which agent and worker are doing what right now?
- What work packet was attempted, and what was the result?
- Is the machine actually producing useful compute, or merely showing a live process?
- What is estimated, what is confirmed, and what has actually been received?
- How far is the system from the current $20 subscription target?
- What changed, when did it change, and where is the supporting evidence?

The owner can answer the same questions locally with more detail through the event ledger, worker logs, and runtime diagnostics.

## First mission shape

The Bitcoin lane will eventually use a worker adapter for a real SHA-256d Stratum miner. It should publish pool and machine evidence such as:

- connection and job lifecycle;
- hashrate and joules per hash;
- shares submitted, accepted, and rejected;
- best share difficulty;
- worker uptime and recovery count;
- GPU utilization, temperature, power, and memory;
- payout estimate, confirmed pool credit, and actual receipt when available.

No mining binary, pool credential, wallet secret, or live payout data is included in this initial repository.

## Visual product direction

The dashboard is a public Mission Control surface, not a log dump. Its first information architecture is:

1. Overview — mission, current state, goal, and the manager-to-worker path.
2. Work — agent activity, work packets, accepted/rejected results, and current hypotheses or job metadata where the worker actually exposes them.
3. Machine proof — GPU/CPU/temperature/power/uptime evidence and freshness.
4. Economics — target, estimated credit, confirmed payout, money received, reserve, and cost quality.
5. Evidence — append-only public timeline with event IDs, actors, outcomes, and source labels.

A future 3D/animated room may make the worker topology memorable, but the canonical truth remains the structured event and telemetry stream.

## Open decisions for later

- Exact name and destination of the new public GitHub repository.
- Which mining pool and whether a solo lane is included after the pool worker is verified.
- Which dedicated receiving address is used for public proof.
- Whether an operator wants public exact or public rounded finance by default.
- The source location and current contents of the separate Live Reference Principle project.
- Which external communication and revenue platforms are worth onboarding after the mining lane has a truthful measurement loop.

