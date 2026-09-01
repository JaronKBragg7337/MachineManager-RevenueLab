"""Append-only local event ledger."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import EventRecord, as_jsonable


class EventLedger:
    """Store complete local events without making the public dashboard the database."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                timestamp TEXT NOT NULL,
                event_json TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def append(self, event: EventRecord) -> None:
        payload = json.dumps(as_jsonable(event), sort_keys=True, separators=(",", ":"))
        self.connection.execute(
            "INSERT INTO events(event_id, timestamp, event_json) VALUES (?, ?, ?)",
            (event.event_id, event.timestamp, payload),
        )
        self.connection.commit()

    def recent(self, limit: int = 100) -> list[EventRecord]:
        rows = self.connection.execute(
            "SELECT event_json FROM events ORDER BY sequence DESC LIMIT ?", (limit,)
        ).fetchall()
        return [EventRecord(**json.loads(row["event_json"])) for row in reversed(rows)]

    def count(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) AS count FROM events").fetchone()
        return int(row["count"])

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "EventLedger":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

