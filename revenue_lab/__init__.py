"""Evidence-first orchestration primitives for MachineManager Revenue Lab."""

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
)
from .state import can_transition, transition
from .workers import BitcoinSha256dStratumSpec, WorkerAdapter, WorkerObservation

__all__ = [
    "AgentSnapshot",
    "EventRecord",
    "FinanceSnapshot",
    "MachineSnapshot",
    "Mission",
    "MissionState",
    "PublicSnapshot",
    "VisibilityMode",
    "WorkPacket",
    "WorkerSnapshot",
    "BitcoinSha256dStratumSpec",
    "WorkerAdapter",
    "WorkerObservation",
    "can_transition",
    "transition",
]
