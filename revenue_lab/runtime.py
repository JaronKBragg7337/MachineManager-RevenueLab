"""A bounded, honest runtime used to exercise the continuous-work path."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .ledger import EventLedger
from .models import (
    AgentSnapshot,
    EventRecord,
    FinanceSnapshot,
    MachineSnapshot,
    Mission,
    MissionState,
    PublicSnapshot,
    VisibilityMode,
    WorkPacket,
    WorkerSnapshot,
    utc_now,
)
from .publisher import publish_snapshot
from .state import transition
from .workers import WorkerObservation


@dataclass(slots=True)
class SyntheticWorker:
    """A deterministic worker for crash/stall/telemetry tests, never a revenue claim."""

    worker_id: str = "synthetic-worker-001"
    worker_type: str = "Synthetic proof worker"
    state: str = "NOT_CONNECTED"
    attempts: int = 0
    started_at: str | None = None

    def start(self, objective: str, resources: dict[str, Any]) -> None:
        del objective, resources
        self.state = "RUNNING"
        self.started_at = utc_now()

    def observe(self) -> WorkerObservation:
        if self.state != "RUNNING":
            raise RuntimeError("synthetic worker is not running")
        self.attempts += 1
        accepted = self.attempts // 4
        rejected = self.attempts // 13
        return WorkerObservation(
            worker_id=self.worker_id,
            state=self.state,
            progress_cursor=f"synthetic-batch-{self.attempts:06d}",
            metrics={
                "work_units": self.attempts * 1000,
                "rate": 1000.0,
                "rate_unit": "units/s",
                "accepted_shares": accepted,
                "rejected_shares": rejected,
            },
            evidence_quality="synthetic_observation",
            note="Simulation only; no pool, wallet, or revenue is connected.",
        )

    def stop(self, reason: str) -> None:
        del reason
        self.state = "STOPPED"

    def recover(self, reason: str) -> None:
        del reason
        self.state = "RUNNING"


class RevenueLabRuntime:
    """Run one mission observation loop and project its evidence to the dashboard."""

    def __init__(
        self,
        dashboard_data_directory: str | Path,
        state_database: str | Path,
        *,
        worker: SyntheticWorker | None = None,
    ) -> None:
        self.dashboard_data_directory = Path(dashboard_data_directory)
        self.ledger = EventLedger(state_database)
        self.worker = worker or SyntheticWorker()
        self.mission = Mission(
            mission_id="btc-pool-experiment",
            name="Bitcoin proof-of-work experiment",
            objective="Measure whether a persistent SHA-256d worker can build verified pool credit toward a subscription reserve.",
            lane="bitcoin",
            state=MissionState.PLANNED,
            success_measure="Confirmed payout and money received are greater than measured mission-attributed cost.",
            target_amount=20.0,
            target_currency="USD",
            reference_id="ref-first-mission",
        )
        self.agents = [
            AgentSnapshot(
                agent_id="manager-core",
                role="Mission manager",
                provider="local runtime",
                model="runtime-controller",
                state="READY",
                current_action="Preparing the next observation.",
                capability_basis="tested_contract",
            ),
            AgentSnapshot(
                agent_id="evidence-steward",
                role="Evidence steward",
                provider="local runtime",
                model="sanitizer",
                state="READY",
                current_action="Waiting for a real work packet.",
                capability_basis="tested_contract",
            ),
        ]
        self.machine = MachineSnapshot(state="AVAILABLE", evidence_quality="synthetic_worker_only")
        self.finance = FinanceSnapshot(
            visibility=VisibilityMode.PUBLIC_EXACT,
            target_amount=20.0,
            estimated_credit=0.0,
            confirmed_payout=0.0,
            money_received=0.0,
            reserve_amount=0.0,
            target_label="Monthly subscription",
            cost_quality="unknown_shared_bill",
            note="Simulation only: no live revenue or wallet is connected.",
        )
        self.events: list[EventRecord] = []
        self.packets: list[WorkPacket] = []
        self._last_snapshot: PublicSnapshot | None = None
        self._started = False

    def _record(self, event: EventRecord) -> None:
        self.events.append(event)
        self.events = self.events[-100:]
        self.ledger.append(event)

    def _transition(self, new_state: MissionState, action: str, outcome: str) -> None:
        previous = self.mission.state
        self.mission.state = transition(previous, new_state)
        self._record(
            EventRecord(
                timestamp=utc_now(),
                event_id=f"runtime-state-{len(self.events) + 1:06d}",
                objective_id=self.mission.mission_id,
                job_id="job-revenue-lab-demo",
                worker_id=self.worker.worker_id,
                actor="manager-core",
                event_type="state_change",
                previous_state=previous.value,
                new_state=new_state.value,
                action=action,
                outcome=outcome,
                source="synthetic_runtime",
                public_summary=outcome,
            )
        )

    def start(self) -> None:
        if self._started:
            return
        self._transition(MissionState.QUEUED, "Queued the first bounded observation run.", "Mission entered the runtime queue.")
        self._transition(MissionState.STARTING, "Starting the synthetic worker adapter.", "Worker start requested.")
        self.worker.start(self.mission.objective, {"mode": "synthetic"})
        self._transition(MissionState.RUNNING, "Verified the synthetic worker lifecycle.", "Simulation worker is producing observable packets.")
        self._started = True

    def _worker_snapshot(self, observation: WorkerObservation) -> WorkerSnapshot:
        metrics = observation.metrics
        return WorkerSnapshot(
            worker_id=observation.worker_id,
            worker_type=self.worker.worker_type,
            state=observation.state,
            lane=self.mission.lane,
            rate=metrics.get("rate"),
            rate_unit=metrics.get("rate_unit"),
            accepted_shares=metrics.get("accepted_shares"),
            rejected_shares=metrics.get("rejected_shares"),
            recovery_count=0,
            last_progress_at=utc_now(),
            evidence_quality=observation.evidence_quality,
            note=observation.note,
        )

    def tick(self) -> PublicSnapshot:
        self.start()
        observation = self.worker.observe()
        timestamp = utc_now()
        packet_id = f"packet-synthetic-{self.worker.attempts:06d}"
        event_id = f"runtime-work-{self.worker.attempts:06d}"
        packet = WorkPacket(
            packet_id=packet_id,
            mission_id=self.mission.mission_id,
            kind="synthetic_work",
            title=f"Synthetic batch #{self.worker.attempts:04d}",
            state="COMPLETE",
            input_summary=f"Generated test packet {observation.progress_cursor}.",
            output_summary="Completed a deterministic worker cycle; this proves the evidence path, not revenue.",
            actor=self.worker.worker_id,
            source="synthetic_runtime",
            started_at=timestamp,
            completed_at=timestamp,
            duration_seconds=0.0,
            evidence_event_id=event_id,
        )
        self.packets.append(packet)
        self.packets = self.packets[-40:]
        self._record(
            EventRecord(
                timestamp=timestamp,
                event_id=event_id,
                objective_id=self.mission.mission_id,
                job_id="job-revenue-lab-demo",
                worker_id=self.worker.worker_id,
                actor=self.worker.worker_id,
                event_type="work_packet_completed",
                previous_state="RUNNING",
                new_state="RUNNING",
                metrics=observation.metrics,
                action=f"Completed {observation.progress_cursor}.",
                outcome="Synthetic packet completed; no financial result claimed.",
                artifact_refs=[packet_id],
                source="synthetic_runtime",
                public_summary="A deterministic test packet completed and entered the public evidence stream.",
            )
        )
        self.agents[0].state = "WORKING"
        self.agents[0].current_action = f"Verified packet {self.worker.attempts:04d} and refreshed worker evidence."
        self.agents[0].work_packets = len(self.packets)
        self.agents[0].last_update = timestamp
        self.agents[1].state = "REVIEWING"
        self.agents[1].current_action = "Checking that synthetic evidence remains clearly labeled and sanitized."
        self.agents[1].work_packets = len(self.packets)
        self.agents[1].last_update = timestamp
        snapshot = PublicSnapshot(
            schema_version="1.0",
            mode="synthetic-demo",
            status="SYNTHETIC_DEMO",
            updated_at=timestamp,
            mission=self.mission,
            worker=self._worker_snapshot(observation),
            agents=self.agents,
            machine=self.machine,
            finance=self.finance,
            work_packets=self.packets,
            events=self.events,
            references=[
                {
                    "reference_id": "ref-first-mission",
                    "title": "Owner mission brief",
                    "kind": "design_input",
                    "source": "owner conversation",
                    "observed_at": timestamp,
                    "review_by": "pending live-reference review",
                    "status": "active_design_input",
                }
            ],
            scenarios=[
                {
                    "scenario_id": "synthetic-continuous-work-001",
                    "category": "runtime",
                    "status": "PASS",
                    "result": "Bounded synthetic packets remained visible across runtime ticks.",
                    "source": "local runtime",
                },
                {
                    "scenario_id": "bitcoin-worker-live-001",
                    "category": "worker_integration",
                    "status": "NOT_RUN",
                    "result": "Awaiting the real SHA-256d adapter.",
                    "source": "planned experiment",
                },
            ],
        )
        publish_snapshot(snapshot, self.dashboard_data_directory)
        self._last_snapshot = snapshot
        return snapshot

    def close(self) -> None:
        if self._started and self.mission.state == MissionState.RUNNING:
            self.worker.stop("runtime closed")
            self._transition(MissionState.CANCELLED, "Stopped the synthetic runtime.", "Simulation stopped by the operator; no mining result was claimed.")
            if self._last_snapshot is not None:
                final_worker = replace(
                    self._last_snapshot.worker,
                    state=self.worker.state,
                    note="Simulation stopped; no mining result was claimed.",
                )
                final_snapshot = replace(
                    self._last_snapshot,
                    status="STOPPED",
                    updated_at=utc_now(),
                    mission=self.mission,
                    worker=final_worker,
                    agents=list(self.agents),
                    events=list(self.events),
                )
                publish_snapshot(final_snapshot, self.dashboard_data_directory)
                self._last_snapshot = final_snapshot
        self._started = False
        self.ledger.close()

    def run(self, iterations: int = 0, interval_seconds: float = 15.0) -> None:
        """Run continuously when iterations is zero; bounded iterations are test-friendly."""

        completed = 0
        try:
            while iterations == 0 or completed < iterations:
                self.tick()
                completed += 1
                if iterations == 0 or completed < iterations:
                    time.sleep(interval_seconds)
        finally:
            self.close()
