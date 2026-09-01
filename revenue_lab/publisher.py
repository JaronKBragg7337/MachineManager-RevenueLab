"""Write sanitized dashboard projections atomically."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .models import PublicSnapshot, as_jsonable
from .privacy import sanitize_snapshot


def _atomic_json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f"{path.stem}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=True)
            handle.write("\n")
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def publish_snapshot(snapshot: PublicSnapshot, data_directory: str | Path) -> dict[str, Path]:
    """Publish latest, event, and scenario projections and return their paths."""

    destination = Path(data_directory)
    public = sanitize_snapshot(snapshot)
    latest_path = destination / "latest.json"
    events_path = destination / "events.json"
    scenarios_path = destination / "scenarios.json"

    _atomic_json_write(latest_path, public)
    _atomic_json_write(events_path, public.get("events", []))
    _atomic_json_write(
        scenarios_path,
        {
            "schema_version": public.get("schema_version", "1.0"),
            "mode": public.get("mode", "preview"),
            "updated_at": public.get("updated_at"),
            "scenarios": public.get("scenarios", []),
        },
    )
    return {"latest": latest_path, "events": events_path, "scenarios": scenarios_path}

