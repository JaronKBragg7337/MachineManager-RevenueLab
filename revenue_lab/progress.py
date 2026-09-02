"""Allowlisted worker-progress parsing for future real adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .workers import WorkerObservation


class ProgressParseError(ValueError):
    """The worker report did not satisfy the small aggregate progress contract."""


PUBLIC_PROGRESS_KEYS = {
    "worker_id",
    "state",
    "progress_cursor",
    "rate",
    "rate_unit",
    "hashes",
    "accepted_shares",
    "rejected_shares",
    "best_share_difficulty",
    "pool_connected",
    "uptime_seconds",
}


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProgressParseError(f"missing aggregate field: {key}")
    return value.strip()


def parse_progress(payload: dict[str, Any]) -> WorkerObservation:
    """Build an observation from allowlisted values and ignore everything else."""

    if not isinstance(payload, dict):
        raise ProgressParseError("worker progress must be an object")
    worker_id = _required_text(payload, "worker_id")
    state = _required_text(payload, "state")
    cursor = payload.get("progress_cursor")
    if cursor is not None and not isinstance(cursor, str):
        raise ProgressParseError("progress_cursor must be text")
    metrics: dict[str, Any] = {}
    for key in PUBLIC_PROGRESS_KEYS - {"worker_id", "state", "progress_cursor"}:
        if key in payload:
            value = payload[key]
            if isinstance(value, (str, int, float, bool)) and not isinstance(value, bytes):
                metrics[key] = value
    return WorkerObservation(
        worker_id=worker_id,
        state=state,
        progress_cursor=cursor,
        metrics=metrics,
        evidence_quality="worker_progress_file",
        note="Parsed from aggregate worker progress fields.",
    )


def read_progress(path: str | Path) -> WorkerObservation:
    """Read one local report; raw contents are never returned in the error."""

    try:
        with Path(path).open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise ProgressParseError("worker progress could not be read") from error
    return parse_progress(payload)
