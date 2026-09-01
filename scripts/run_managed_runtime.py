"""Run the reusable manager as a local, bounded or continuous service."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from revenue_lab.manager import ManagerPolicy, MissionManager  # noqa: E402
from revenue_lab.models import AgentSnapshot, FinanceSnapshot, Mission, MissionState, VisibilityMode  # noqa: E402
from revenue_lab.synthetic import SUPPORTED_SCENARIOS, ScenarioWorker  # noqa: E402


def build_manager(args: argparse.Namespace) -> MissionManager:
    mission = Mission(
        mission_id="managed-runtime-demo",
        name="Revenue Lab managed runtime demo",
        objective="Exercise continuous evidence collection through the reusable mission manager.",
        lane="synthetic",
        state=MissionState.PLANNED,
        success_measure="The service publishes fresh progress and bounded recovery evidence.",
        target_amount=None,
    )
    agents = [
        AgentSnapshot(
            agent_id="manager-core",
            role="Mission manager",
            provider="local runtime",
            model="manager-controller",
            state="READY",
            current_action="Preparing the managed runtime.",
            capability_basis="tested_contract",
        ),
        AgentSnapshot(
            agent_id="evidence-steward",
            role="Evidence steward",
            provider="local runtime",
            model="sanitizer",
            state="READY",
            current_action="Waiting for the first packet.",
            capability_basis="tested_contract",
        ),
    ]
    return MissionManager(
        mission,
        ScenarioWorker(scenario=args.scenario, worker_id="managed-synthetic-worker"),
        agents,
        args.dashboard_data,
        args.state_db,
        finance=FinanceSnapshot(
            visibility=VisibilityMode.PRIVATE,
            target_amount=None,
            note="Synthetic service only; no pool, wallet, or revenue is connected.",
        ),
        policy=ManagerPolicy(
            stall_after_observations=args.stall_after,
            max_recoveries=args.max_recoveries,
        ),
        mode="managed-synthetic-service",
        references=[
            {
                "reference_id": "ref-manager-runtime",
                "title": "Reusable manager runtime",
                "kind": "local_build",
                "source": "Revenue Lab repository",
                "status": "active",
            }
        ],
        scenarios=[
            {
                "scenario_id": "managed-runtime-live-001",
                "category": "local_service",
                "status": "RUNNING",
                "result": "A local synthetic service is publishing manager evidence.",
                "source": "local runtime",
            }
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SUPPORTED_SCENARIOS, default="healthy")
    parser.add_argument("--iterations", type=int, default=0, help="ticks to run; 0 keeps running")
    parser.add_argument("--interval", type=float, default=15.0, help="seconds between ticks")
    parser.add_argument("--stall-after", type=int, default=3)
    parser.add_argument("--max-recoveries", type=int, default=2)
    parser.add_argument(
        "--dashboard-data",
        type=Path,
        default=PROJECT_ROOT / "runtime" / "managed-dashboard",
        help="local JSON projection directory",
    )
    parser.add_argument(
        "--state-db",
        type=Path,
        default=PROJECT_ROOT / "runtime" / "managed-events.sqlite3",
        help="local SQLite event ledger",
    )
    args = parser.parse_args()
    if args.iterations < 0:
        parser.error("--iterations cannot be negative")
    if args.interval < 0:
        parser.error("--interval cannot be negative")

    manager = build_manager(args)
    print("Revenue Lab managed runtime started; this service uses synthetic evidence only.")
    completed = 0
    try:
        while args.iterations == 0 or completed < args.iterations:
            snapshot = manager.tick()
            completed += 1
            print(
                f"cycle={completed} status={snapshot.status} "
                f"packets={len(snapshot.work_packets)} "
                f"recoveries={snapshot.worker.recovery_count if snapshot.worker else 0}"
            )
            if snapshot.mission.state is MissionState.ESCALATED:
                break
            if args.iterations == 0 or completed < args.iterations:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("shutdown requested")
    finally:
        manager.close()
    print("Revenue Lab managed runtime stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
