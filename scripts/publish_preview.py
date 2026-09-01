"""Publish the honest local dashboard preview."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from revenue_lab.preview import build_preview_snapshot  # noqa: E402
from revenue_lab.publisher import publish_snapshot  # noqa: E402


def main() -> int:
    paths = publish_snapshot(build_preview_snapshot(), PROJECT_ROOT / "dashboard" / "data")
    for name, path in paths.items():
        print(f"published {name}: {path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

