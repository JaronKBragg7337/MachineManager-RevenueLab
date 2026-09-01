"""Evidence-backed capability records for model and tool onboarding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .models import utc_now


CapabilityStatus = Literal["observed", "tested_pass", "tested_fail", "unknown"]


@dataclass(slots=True)
class CapabilityRecord:
    worker_id: str
    capability: str
    status: CapabilityStatus
    evidence_ref: str
    observed_at: str
    review_by: str | None = None
    note: str = ""


def capability_record(
    worker_id: str,
    capability: str,
    status: CapabilityStatus,
    evidence_ref: str,
    *,
    review_by: str | None = None,
    note: str = "",
) -> CapabilityRecord:
    return CapabilityRecord(
        worker_id=worker_id,
        capability=capability,
        status=status,
        evidence_ref=evidence_ref,
        observed_at=utc_now(),
        review_by=review_by,
        note=note,
    )

