"""Worker adapter boundaries; implementations arrive after the contract is tested."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class WorkerObservation:
    worker_id: str
    state: str
    progress_cursor: str | None
    metrics: dict[str, Any] = field(default_factory=dict)
    evidence_quality: str = "observed"
    note: str = ""


class WorkerAdapter(Protocol):
    """Common lifecycle expected by the mission manager."""

    worker_id: str
    worker_type: str

    def start(self, objective: str, resources: dict[str, Any]) -> None:
        ...

    def observe(self) -> WorkerObservation:
        ...

    def stop(self, reason: str) -> None:
        ...

    def recover(self, reason: str) -> None:
        ...


@dataclass(frozen=True, slots=True)
class BitcoinSha256dStratumSpec:
    """The first adapter's observable contract, independent of a vendor binary."""

    adapter_id: str = "bitcoin-sha256d-stratum"
    lane: str = "bitcoin"
    algorithm: str = "SHA-256d"
    protocol: str = "Stratum"
    required_metrics: tuple[str, ...] = (
        "hashrate",
        "accepted_shares",
        "rejected_shares",
        "best_share_difficulty",
        "pool_connected",
    )
    machine_metrics: tuple[str, ...] = (
        "gpu_utilization_pct",
        "gpu_temperature_c",
        "gpu_power_w",
        "vram_used_gb",
    )

