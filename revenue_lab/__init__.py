"""Evidence-first orchestration primitives for MachineManager Revenue Lab."""

from .models import (
    AgentSnapshot,
    EventRecord,
    FinanceSnapshot,
    MachineSnapshot,
    Mission,
    MissionState,
    PublicSnapshot,
    ReceiptClassification,
    ReceiptRecord,
    VisibilityMode,
    WorkPacket,
    WorkerSnapshot,
)
from .state import can_transition, transition
from .workers import BitcoinSha256dStratumSpec, WorkerAdapter, WorkerObservation
from .probes import parse_nvidia_csv, sample_nvidia
from .progress import ProgressParseError, parse_progress, read_progress
from .process_worker import ProcessWorkerAdapter, ProcessWorkerSpec
from .finance import can_propose_return, classify_receipt, mark_return_proposed

__all__ = [
    "AgentSnapshot",
    "EventRecord",
    "FinanceSnapshot",
    "MachineSnapshot",
    "Mission",
    "MissionState",
    "PublicSnapshot",
    "ReceiptClassification",
    "ReceiptRecord",
    "VisibilityMode",
    "WorkPacket",
    "WorkerSnapshot",
    "BitcoinSha256dStratumSpec",
    "WorkerAdapter",
    "WorkerObservation",
    "can_transition",
    "transition",
    "parse_nvidia_csv",
    "sample_nvidia",
    "ProgressParseError",
    "parse_progress",
    "read_progress",
    "ProcessWorkerAdapter",
    "ProcessWorkerSpec",
    "can_propose_return",
    "classify_receipt",
    "mark_return_proposed",
]
