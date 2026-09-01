"""Validate the three files that may be published to a public dashboard."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from revenue_lab.privacy import validate_public_payload  # noqa: E402


def main() -> int:
    data_directory = PROJECT_ROOT / "dashboard" / "data"
    required = ("latest.json", "events.json", "scenarios.json")
    for filename in required:
        path = data_directory / filename
        if not path.is_file():
            raise SystemExit(f"missing public data file: {path}")
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        validate_public_payload(payload)
        print(f"validated {filename}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

