"""Reusable mission manager for persistent, evidence-first work.

The manager owns the control loop, not the mission's specialist algorithm.  A
worker must provide a fresh aggregate progress cursor; process liveness alone
is deliberately treated as insufficient evidence of useful work.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable
from uuid import uuid4

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
from .workers import WorkerAdapter, WorkerObservation


MachineSampler = Callable[[], MachineSnapshot]


@dataclass(frozen=True, slots=True)
class ManagerPolicy:
    """Bound recovery and define how much stale evidence becomes a stall."""

    stall_after_observations: int = 3
    max_recoveries: int = 2
    event_history: int = 100

    def __post_init__(self) -> None:
        if self.stall_after_observations < 1:
            raise ValueError("stall_after_observations must be at least one")
        if self.max_recoveries < 0:
            raise ValueError("max_recoveries cannot be negative")
        if self.event_history < 1:
            raise ValueError("event_history must be at least one")


_PUBLIC_METRIC_KEYS = {
    "rate",
    "rate_unit",
    "hashrate",
    "hashrate_unit",
    "accepted_shares",
    "rejected_shares",
    "best_share_difficulty",
    "pool_connected",
    "work_units",
    "work_units_unit",
    "uptime_seconds",
}


def _public_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """Keep only scalar aggregate metrics suitable for a public snapshot."""

    result: dict[str, Any] = {}
    for key, value in metrics.items():
        if key not in _PUBLIC_METRIC_KEYS:
            continue
        if isinstance(value, (bool, int, float, str)) or value is None:
            result[key] = value
    return result


class MissionManager:
    """Run one mission through a worker adapter and publish every observation.

    This class intentionally has no Bitcoin-specific launch command and no
    model-provider dependency.  A future lane supplies a WorkerAdapter and can
    add an AI agent around the same evidence contract.
    """

    def __init__(
        self,
        mission: Mission,
        worker: WorkerAdapter,
        agents: Iterable[AgentSnapshot],
        dashboard_data_directory: str | Path,
        state_database: str | Path,
        *,
        finance: FinanceSnapshot | None = None,
        machine_sampler: MachineSampler | None = None,
        references: list[dict[str, Any]] | None = None,
        scenarios: list[dict[str, Any]] | None = None,
        policy: ManagerPolicy | None = None,
        job_id: str = "job-revenue-lab-managed",
        mode: str = "managed-runtime",
    ) -> None:
        self.mission = replace(mission)
        self.worker = worker
        self.agents = [replace(agent) for agent in agents]
        self.dashboard_data_directory = Path(dashboard_data_directory)
        self.ledger = EventLedger(state_database)
        self.policy = policy or ManagerPolicy()
        self.finance = replace(finance) if finance is not None else FinanceSnapshot(
            visibility=VisibilityMode.PRIVATE,
            note="No live financial source is connected.",
        )
        self.machine_sampler = machine_sampler
        self.references = list(references or [])
        self.scenarios = list(scenarios or [])
        self.job_id = job_id
        self.mode = mode

        self.events = self.ledger.recent(self.policy.event_history)
        self.packets: list[WorkPacket] = []
        self.machine = MachineSnapshot(state="AVAILABLE", evidence_quality="awaiting_worker")
        self.recovery_count = 0
        self._no_progress_observations = 0
        self._last_cursor: str | None = None
        self._last_progress_at: str | None = None
        self._last_observation: WorkerObservation | None = None
        self._cycle = 0
        self._worker_state = "NOT_CONNECTED"
        self._started = False
        self._closed = False
        self._last_snapshot: PublicSnapshot | None = None

    def _event_id(self, prefix: str) -> str:
        return f"{prefix}-{uuid4().hex[:12]}"

    def _record(self, event: EventRecord) -> None:
        self.events.append(event)
        self.events = self.events[-self.policy.event_history :]
        self.ledger.append(event)

    def _event(
        self,
        event_type: str,
        *,
        actor: str = "manager-core",
        metrics: dict[str, Any] | None = None,
        action: str = "",
        outcome: str = "",
        error: str | None = None,
        public_summary: str | None = None,
        artifact_refs: list[str] | None = None,
        previous_state: str | None = None,
        new_state: str | None = None,
    ) -> EventRecord:
        event = EventRecord(
            timestamp=utc_now(),
            event_id=self._event_id(event_type),
            objective_id=self.mission.mission_id,
            job_id=self.job_id,
            worker_id=self.worker.worker_id,
            actor=actor,
            event_type=event_type,
            previous_state=previous_state,
            new_state=new_state,
            metrics=_public_metrics(metrics or {}),
            action=action,
            outcome=outcome,
            artifact_refs=artifact_refs or [],
            error=error,
            source=self.mode,
            public_summary=public_summary,
        )
        self._record(event)
        return event

    def _transition(self, new_state: MissionState, action: str, outcome: str) -> None:
        previous = self.mission.state
        self.mission.state = transition(previous, new_state)
        self._event(
            "state_change",
            action=action,
            outcome=outcome,
            public_summary=outcome,
            previous_state=previous.value,
            new_state=new_state.value,
        )

    def _sample_machine(self) -> None:
        if self.machine_sampler is None:
            return
        try:
            sampled = self.machine_sampler()
        except Exception:
            self.machine = replace(
                self.machine,
                state="UNKNOWN",
                evidence_quality="probe_error",
                sampled_at=utc_now(),
            )
            self._event(
                "machine_probe_failed",
                action="Requested a machine telemetry sample.",
                outcome="Worker evidence remains separate from the unavailable machine probe.",
                error="machine_probe_failed",
                public_summary="Machine telemetry was unavailable for this observation.",
            )
            return
        self.machine = sampled

    def _worker_snapshot(self) -> WorkerSnapshot:
        observation = self._last_observation
        metrics = observation.metrics if observation is not None else {}
        return WorkerSnapshot(
            worker_id=self.worker.worker_id,
            worker_type=self.worker.worker_type,
            state=self._worker_state,
            lane=self.mission.lane,
            rate=metrics.get("rate", metrics.get("hashrate")),
            rate_unit=metrics.get("rate_unit", metrics.get("hashrate_unit")),
            accepted_shares=metrics.get("accepted_shares"),
            rejected_shares=metrics.get("rejected_shares"),
            best_share_difficulty=metrics.get("best_share_difficulty"),
            pool_name=metrics.get("pool_name"),
            uptime_seconds=metrics.get("uptime_seconds"),
            recovery_count=self.recovery_count,
            last_progress_at=self._last_progress_at,
            evidence_quality=observation.evidence_quality if observation else "not_started",
            note=observation.note if observation else "The worker has not produced an observation yet.",
        )

    def _update_agents(self, action: str, timestamp: str) -> None:
        for agent in self.agents:
            if agent.agent_id == "manager-core":
                agent.state = "WORKING" if self.mission.state == MissionState.RUNNING else self.mission.state.value
                agent.current_action = action
                agent.work_packets = len(self.packets)
                agent.last_update = timestamp
            elif agent.agent_id == "evidence-steward":
                agent.state = "REVIEWING"
                agent.current_action = "Checking aggregate evidence before it enters the public projection."
                agent.work_packets = len(self.packets)
                agent.last_update = timestamp

    def _publish(self, *, status: str | None = None) -> PublicSnapshot:
        timestamp = utc_now()
        snapshot = PublicSnapshot(
            schema_version="1.0",
            mode=self.mode,
            status=status or self.mission.state.value,
            updated_at=timestamp,
            mission=deepcopy(self.mission),
            worker=self._worker_snapshot(),
            agents=deepcopy(self.agents),
            machine=deepcopy(self.machine),
            finance=deepcopy(self.finance),
            work_packets=deepcopy(self.packets),
            events=deepcopy(self.events),
            references=deepcopy(self.references),
            scenarios=deepcopy(self.scenarios),
        )
        publish_snapshot(snapshot, self.dashboard_data_directory)
        self._last_snapshot = snapshot
        return snapshot

    def _append_packet(self, observation: WorkerObservation, *, fresh: bool) -> WorkPacket:
        packet_id = f"packet-{self._cycle:06d}-{uuid4().hex[:8]}"
        event = self._event(
            "worker_progress" if fresh else "worker_observation",
            actor=self.worker.worker_id,
            metrics=observation.metrics,
            action="Recorded a fresh aggregate progress cursor." if fresh else "Recorded a worker health observation.",
            outcome=(
                "Fresh progress was observed and the packet is useful-work evidence."
                if fresh
                else "The process responded, but this observation did not advance the aggregate cursor."
            ),
            artifact_refs=[packet_id],
            public_summary=(
                "A fresh worker progress packet completed."
                if fresh
                else "A worker observation was recorded while waiting for fresh progress."
            ),
        )
        packet = WorkPacket(
            packet_id=packet_id,
            mission_id=self.mission.mission_id,
            kind="worker_progress" if fresh else "worker_observation",
            title=f"Worker observation #{self._cycle:04d}",
            state="COMPLETE" if fresh else "OBSERVED",
            input_summary="Read the worker's aggregate progress report and machine-independent metrics.",
            output_summary=(
                "Fresh progress cursor advanced; evidence is suitable for a useful-work check."
                if fresh
                else "No new progress cursor was available in this observation."
            ),
            actor=self.worker.worker_id,
            source=self.mode,
            started_at=event.timestamp,
            completed_at=event.timestamp,
            duration_seconds=0.0,
            evidence_event_id=event.event_id,
        )
        self.packets.append(packet)
        self.packets = self.packets[-40:]
        return packet

    def _escalate(self, reason: str) -> None:
        if self.mission.state != MissionState.ESCALATED:
            self._transition(
                MissionState.ESCALATED,
                "Stopped bounded recovery after the configured limit.",
                "The manager escalated instead of restarting indefinitely.",
            )
        self._worker_state = "ESCALATED"
        try:
            self.worker.stop("bounded recovery exhausted")
        except Exception:
            self._event(
                "worker_stop_failed",
                action="Attempted to stop an escalated worker.",
                outcome="The worker stop call failed; the manager remains escalated.",
                error="worker_stop_failed",
                public_summary="The manager escalated; worker stop confirmation was unavailable.",
            )
        self._event(
            "manager_escalated",
            action="Recorded the recovery boundary.",
            outcome="Human or executive direction is required before another attempt.",
            error=reason,
            public_summary="Bounded recovery was exhausted and the mission is escalated.",
        )

    def _handle_unhealthy(self, kind: str, reason: str) -> None:
        target = MissionState.STALLED if kind == "stall" else MissionState.FAILED
        if self.mission.state in {MissionState.RUNNING, MissionState.STARTING}:
            self._transition(
                target,
                "Marked the worker unhealthy from multi-signal evidence.",
                "The worker did not provide sufficiently fresh useful-work evidence.",
            )
        if self.recovery_count >= self.policy.max_recoveries:
            self._escalate(f"{kind}_recovery_exhausted")
            return

        self._transition(
            MissionState.RETRYING,
            "Scheduled one bounded worker recovery.",
            "The manager will retry the worker within the configured recovery limit.",
        )
        self.recovery_count += 1
        self._event(
            "worker_recovery_started",
            action="Requested bounded worker recovery.",
            outcome="Recovery attempt started.",
            error=f"{kind}_detected",
            public_summary="The manager started a bounded recovery after stale or failed evidence.",
        )
        try:
            self.worker.recover(reason)
        except Exception:
            self._worker_state = "FAILED"
            self._transition(
                MissionState.STARTING,
                "Returned to the worker start phase after recovery failure.",
                "The next observation will determine whether another bounded attempt is available.",
            )
            self._event(
                "worker_recovery_failed",
                action="Attempted to recover the worker.",
                outcome="The recovery call failed; the manager retained the failure evidence.",
                error="worker_recovery_failed",
                public_summary="A worker recovery attempt failed.",
            )
            return

        self._worker_state = "RUNNING"
        self._last_cursor = None
        self._no_progress_observations = 0
        self._last_progress_at = None
        self._transition(
            MissionState.STARTING,
            "Verified the worker recovery call returned.",
            "The worker is being checked again for useful progress.",
        )
        self._transition(
            MissionState.RUNNING,
            "Resumed the mission after bounded recovery.",
            "The manager resumed observation without executive intervention.",
        )

    def start(self) -> PublicSnapshot:
        """Start the worker once and publish the initial state."""

        if self._closed:
            raise RuntimeError("manager is closed")
        if self._started:
            return self._publish()
        if self.mission.state == MissionState.PLANNED:
            self._transition(
                MissionState.QUEUED,
                "Queued the mission for a worker start.",
                "Mission entered the manager queue.",
            )
        self._transition(
            MissionState.STARTING,
            "Starting the configured worker adapter.",
            "Worker start requested; useful work is not assumed yet.",
        )
        try:
            self.worker.start(self.mission.objective, {"lane": self.mission.lane, "mode": self.mode})
        except Exception:
            self._worker_state = "FAILED"
            self._transition(
                MissionState.FAILED,
                "Recorded a worker start failure.",
                "The worker did not start successfully.",
            )
            self._handle_unhealthy("failure", "worker_start_failed")
        else:
            self._worker_state = "RUNNING"
            self._transition(
                MissionState.RUNNING,
                "Verified the worker start call returned.",
                "The manager will require fresh progress before calling the work useful.",
            )
            self._event(
                "worker_started",
                action="Started the worker adapter.",
                outcome="Worker lifecycle started; progress evidence is pending.",
                public_summary="The manager started the specialist worker and is waiting for fresh evidence.",
            )
        self._started = self.mission.state not in {MissionState.ESCALATED, MissionState.CANCELLED}
        return self._publish()

    def tick(self) -> PublicSnapshot:
        """Observe one cycle, recover bounded failures, and publish the result."""

        if self._closed:
            raise RuntimeError("manager is closed")
        if not self._started:
            self.start()
        if self.mission.state != MissionState.RUNNING:
            return self._publish()

        self._cycle += 1
        try:
            observation = self.worker.observe()
        except Exception:
            self._worker_state = "FAILED"
            self._handle_unhealthy("failure", "worker_observation_failed")
            self._sample_machine()
            return self._publish()

        self._last_observation = observation
        self._worker_state = observation.state
        metrics = _public_metrics(observation.metrics)
        cursor_changed = (
            observation.progress_cursor is not None
            and observation.progress_cursor != self._last_cursor
        )
        if observation.state == "FAILED":
            self._append_packet(observation, fresh=False)
            self._handle_unhealthy("failure", "worker_reported_failed")
        elif observation.state == "STALLED":
            self._append_packet(observation, fresh=False)
            self._handle_unhealthy("stall", "worker_reported_stalled")
        elif cursor_changed:
            self._last_cursor = observation.progress_cursor
            self._no_progress_observations = 0
            self._last_progress_at = utc_now()
            self._append_packet(observation, fresh=True)
            self._event(
                "health_check",
                metrics=metrics,
                action="Compared the new aggregate cursor with the prior observation.",
                outcome="Worker is healthy: process response and useful progress both advanced.",
                public_summary="Worker health check passed with fresh useful-work evidence.",
            )
            self._update_agents("Verified fresh worker progress and published the evidence packet.", utc_now())
        else:
            self._no_progress_observations += 1
            self._append_packet(observation, fresh=False)
            self._event(
                "health_check",
                metrics=metrics,
                action="Compared the aggregate cursor with the prior observation.",
                outcome="Process response was observed, but the useful-work cursor did not advance.",
                public_summary="Worker responded without fresh progress; the manager is watching for a stall.",
            )
            self._update_agents("Watching for fresh progress after a non-advancing observation.", utc_now())
            if self._no_progress_observations >= self.policy.stall_after_observations:
                self._handle_unhealthy("stall", "no_fresh_progress")

        self._sample_machine()
        return self._publish()

    def close(self) -> PublicSnapshot:
        """Stop the worker and leave a durable, published shutdown event."""

        if self._closed:
            return self._last_snapshot or self._publish(status="STOPPED")
        if self._started and self.mission.state not in {MissionState.COMPLETE, MissionState.CANCELLED}:
            try:
                self.worker.stop("manager closed")
            except Exception:
                self._event(
                    "worker_stop_failed",
                    action="Attempted to stop the worker during manager shutdown.",
                    outcome="The shutdown call failed; the final public status records the manager stop.",
                    error="worker_stop_failed",
                    public_summary="The manager stopped, but worker shutdown confirmation was unavailable.",
                )
            self._worker_state = "STOPPED"
            if self.mission.state != MissionState.CANCELLED:
                self._transition(
                    MissionState.CANCELLED,
                    "Stopped the managed mission.",
                    "The manager was closed by the operator; no financial result was inferred.",
                )
        self._event(
            "manager_stopped",
            action="Published the manager shutdown checkpoint.",
            outcome="The local ledger retains the complete event history for this run.",
            public_summary="Manager shutdown was recorded in the evidence timeline.",
        )
        self._closed = True
        final = self._publish(status="STOPPED")
        self.ledger.close()
        return final
