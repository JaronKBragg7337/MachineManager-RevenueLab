"""Run the synthetic continuous-work path for dashboard and recovery testing."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from revenue_lab.runtime import RevenueLabRuntime  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=0, help="ticks to run; 0 keeps running")
    parser.add_argument("--interval", type=float, default=15.0, help="seconds between ticks")
    parser.add_argument("--state-db", type=Path, default=PROJECT_ROOT / "runtime" / "events.sqlite3")
    args = parser.parse_args()
    if args.iterations < 0:
        parser.error("--iterations cannot be negative")
    runtime = RevenueLabRuntime(PROJECT_ROOT / "dashboard" / "data", args.state_db)
    print("Revenue Lab synthetic runtime started; dashboard data is simulation-only.")
    runtime.run(iterations=args.iterations, interval_seconds=args.interval)
    print("Revenue Lab synthetic runtime stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

