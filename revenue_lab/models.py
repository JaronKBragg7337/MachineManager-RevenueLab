"""Small, dependency-free data contracts shared by the manager and dashboard."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


def utc_now() -> str:
    """Return a sortable UTC timestamp without a local machine path or identity."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class MissionState(StrEnum):
    PLANNED = "PLANNED"
    QUEUED = "QUEUED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    COMPLETE = "COMPLETE"
    STALLED = "STALLED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    ESCALATED = "ESCALATED"
    CANCELLED = "CANCELLED"


class VisibilityMode(StrEnum):
    PUBLIC_EXACT = "public_exact"
    PUBLIC_ROUNDED = "public_rounded"
    MASKED = "masked"
    PRIVATE = "private"


@dataclass(slots=True)
class Mission:
    mission_id: str
    name: str
    objective: str
    lane: str
    state: MissionState = MissionState.PLANNED
    success_measure: str = ""
    target_amount: float | None = 20.0
    target_currency: str = "USD"
    created_at: str = field(default_factory=utc_now)
    reference_id: str | None = None


@dataclass(slots=True)
class WorkPacket:
    packet_id: str
    mission_id: str
    kind: str
    title: str
    state: str
    input_summary: str
    output_summary: str
    actor: str
    source: str
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None
    evidence_event_id: str | None = None


@dataclass(slots=True)
class AgentSnapshot:
    agent_id: str
    role: str
    provider: str
    model: str
    state: str
    current_action: str
    work_packets: int = 0
    last_update: str | None = None
    capability_basis: str = "observed"


@dataclass(slots=True)
class WorkerSnapshot:
    worker_id: str
    worker_type: str
    state: str
    lane: str
    rate: float | None = None
    rate_unit: str | None = None
    accepted_shares: int | None = None
    rejected_shares: int | None = None
    best_share_difficulty: float | None = None
    pool_name: str | None = None
    uptime_seconds: int | None = None
    recovery_count: int = 0
    last_progress_at: str | None = None
    evidence_quality: str = "awaiting_worker"
    note: str = ""


@dataclass(slots=True)
class MachineSnapshot:
    state: str
    gpu_utilization_pct: float | None = None
    gpu_temperature_c: float | None = None
    gpu_power_w: float | None = None
    vram_used_gb: float | None = None
    vram_total_gb: float | None = None
    cpu_utilization_pct: float | None = None
    uptime_hours: float | None = None
    sampled_at: str | None = None
    evidence_quality: str = "awaiting_worker"


@dataclass(slots=True)
class FinanceSnapshot:
    visibility: VisibilityMode = VisibilityMode.PRIVATE
    currency: str = "USD"
    target_amount: float | None = 20.0
    estimated_credit: float | None = 0.0
    confirmed_payout: float | None = 0.0
    money_received: float | None = 0.0
    reserve_amount: float | None = 0.0
    target_label: str = "Monthly subscription"
    cost_quality: str = "unknown_shared_bill"
    wallet_label: str | None = None
    wallet_public_address: str | None = None
    wallet_balance: float | None = None
    last_payout_at: str | None = None
    note: str = ""


@dataclass(slots=True)
class EventRecord:
    timestamp: str
    event_id: str
    objective_id: str
    job_id: str | None
    worker_id: str | None
    actor: str
    event_type: str
    previous_state: str | None = None
    new_state: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    action: str = ""
    outcome: str = ""
    artifact_refs: list[str] = field(default_factory=list)
    error: str | None = None
    duration: float | None = None
    source: str = "local"
    public_summary: str | None = None


@dataclass(slots=True)
class PublicSnapshot:
    schema_version: str
    mode: str
    status: str
    updated_at: str
    mission: Mission
    worker: WorkerSnapshot | None
    agents: list[AgentSnapshot]
    machine: MachineSnapshot
    finance: FinanceSnapshot
    work_packets: list[WorkPacket]
    events: list[EventRecord]
    references: list[dict[str, Any]] = field(default_factory=list)
    scenarios: list[dict[str, Any]] = field(default_factory=list)


def as_jsonable(value: Any) -> Any:
    """Convert model instances to JSON-compatible values recursively."""

    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value):
        return {key: as_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): as_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_jsonable(item) for item in value]
    return value

