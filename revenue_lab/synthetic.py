"""Deterministic workers for exercising manager failure paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import utc_now
from .workers import WorkerObservation


SUPPORTED_SCENARIOS = (
    "healthy",
    "crash_once",
    "stall_once",
    "false_liveness_once",
    "repeat_failure",
)


@dataclass(slots=True)
class ScenarioWorker:
    """A tiny adapter whose failure mode is explicit and reproducible.

    The worker never connects to a pool, wallet, or external service.  It is
    used to prove the manager's recovery behavior before a real worker is
    allowed to use machine resources.
    """

    scenario: str = "healthy"
    worker_id: str = "synthetic-scenario-001"
    worker_type: str = "Synthetic reliability worker"
    state: str = "NOT_CONNECTED"
    observations: int = 0
    recovery_count: int = 0
    starts: int = 0
    stops: int = 0
    started_at: str | None = None

    def __post_init__(self) -> None:
        if self.scenario not in SUPPORTED_SCENARIOS:
            raise ValueError(f"unsupported scenario: {self.scenario}")

    def start(self, objective: str, resources: dict[str, Any]) -> None:
        del objective, resources
        self.starts += 1
        self.state = "RUNNING"
        self.started_at = utc_now()

    def observe(self) -> WorkerObservation:
        if self.state != "RUNNING":
            raise RuntimeError("scenario worker is not running")
        self.observations += 1

        if self.scenario == "crash_once" and self.recovery_count == 0:
            self.state = "FAILED"
            return WorkerObservation(
                worker_id=self.worker_id,
                state="FAILED",
                progress_cursor=None,
                evidence_quality="synthetic_failure",
                note="Synthetic crash signal; no external work was performed.",
            )

        if self.scenario == "repeat_failure":
            self.state = "FAILED"
            return WorkerObservation(
                worker_id=self.worker_id,
                state="FAILED",
                progress_cursor=None,
                evidence_quality="synthetic_failure",
                note="Synthetic repeated failure; no external work was performed.",
            )

        if self.scenario == "stall_once" and self.recovery_count == 0:
            return WorkerObservation(
                worker_id=self.worker_id,
                state="RUNNING",
                progress_cursor="stalled-cursor",
                metrics={"rate": 100.0, "rate_unit": "units/s", "work_units": 100},
                evidence_quality="synthetic_stall",
                note="Synthetic alive-but-stalled signal; no external work was performed.",
            )

        if self.scenario == "false_liveness_once" and self.recovery_count == 0:
            return WorkerObservation(
                worker_id=self.worker_id,
                state="RUNNING",
                progress_cursor=None,
                metrics={"rate": 0.0, "rate_unit": "units/s"},
                evidence_quality="process_only",
                note="Synthetic process-only signal; liveness is not useful-work proof.",
            )

        return WorkerObservation(
            worker_id=self.worker_id,
            state="RUNNING",
            progress_cursor=f"scenario-batch-{self.observations:06d}",
            metrics={
                "rate": 100.0,
                "rate_unit": "units/s",
                "work_units": self.observations * 100,
                "accepted_shares": self.observations // 4,
                "rejected_shares": 0,
            },
            evidence_quality="synthetic_observation",
            note="Simulation only; no pool, wallet, or revenue is connected.",
        )

    def stop(self, reason: str) -> None:
        del reason
        self.stops += 1
        self.state = "STOPPED"

    def recover(self, reason: str) -> None:
        del reason
        self.recovery_count += 1
        self.state = "RUNNING"
