"""Run bounded manager reliability scenarios and write a local report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from revenue_lab.manager import ManagerPolicy, MissionManager
from revenue_lab.models import AgentSnapshot, FinanceSnapshot, Mission, MissionState, VisibilityMode, as_jsonable
from revenue_lab.synthetic import SUPPORTED_SCENARIOS, ScenarioWorker


def build_manager(scenario: str, root: Path, *, stall_after: int, max_recoveries: int) -> MissionManager:
    mission = Mission(
        mission_id=f"reliability-{scenario}",
        name=f"Manager reliability scenario: {scenario}",
        objective="Exercise the generic manager against a deterministic worker failure mode.",
        lane="synthetic",
        state=MissionState.PLANNED,
        success_measure="The manager records the observed outcome and obeys the recovery bound.",
        target_amount=None,
        target_currency="USD",
    )
    agents = [
        AgentSnapshot(
            agent_id="manager-core",
            role="Mission manager",
            provider="local runtime",
            model="manager-controller",
            state="READY",
            current_action="Preparing the reliability scenario.",
            capability_basis="tested_contract",
        ),
        AgentSnapshot(
            agent_id="evidence-steward",
            role="Evidence steward",
            provider="local runtime",
            model="sanitizer",
            state="READY",
            current_action="Waiting for scenario evidence.",
            capability_basis="tested_contract",
        ),
    ]
    return MissionManager(
        mission,
        ScenarioWorker(scenario=scenario, worker_id=f"synthetic-{scenario}"),
        agents,
        root / "dashboard-data",
        root / "state.sqlite3",
        finance=FinanceSnapshot(
            visibility=VisibilityMode.PRIVATE,
            target_amount=None,
            note="Synthetic reliability scenario; no financial source is connected.",
        ),
        policy=ManagerPolicy(
            stall_after_observations=stall_after,
            max_recoveries=max_recoveries,
        ),
        references=[
            {
                "reference_id": "ref-reliability-contract",
                "title": "Manager reliability contract",
                "kind": "local_test",
                "source": "local build",
                "status": "active",
            }
        ],
        scenarios=[
            {
                "scenario_id": f"manager-{scenario}-001",
                "category": "manager_reliability",
                "status": "RUNNING",
                "result": "Scenario result is written to the local report after execution.",
                "source": "local test runtime",
            }
        ],
        job_id=f"job-reliability-{scenario}",
        mode="reliability-scenario",
    )


def run_scenario(scenario: str, output_root: Path, args: argparse.Namespace) -> dict[str, object]:
    root = output_root / scenario
    manager = build_manager(
        scenario,
        root,
        stall_after=args.stall_after,
        max_recoveries=args.max_recoveries,
    )
    snapshots = []
    try:
        for _ in range(args.iterations):
            snapshot = manager.tick()
            snapshots.append(
                {
                    "status": snapshot.status,
                    "mission_state": snapshot.mission.state.value,
                    "worker_state": snapshot.worker.state if snapshot.worker else None,
                    "packets": len(snapshot.work_packets),
                    "events": len(snapshot.events),
                    "recoveries": snapshot.worker.recovery_count if snapshot.worker else 0,
                }
            )
            if snapshot.mission.state is MissionState.ESCALATED:
                break
        observed_state = manager.mission.state.value
        observed_recoveries = manager.recovery_count
        observed_packets = len(manager.packets)
        observed_events = len(manager.events)
    finally:
        manager.close()

    if observed_state == MissionState.ESCALATED.value:
        outcome = "ESCALATED"
    elif observed_recoveries:
        outcome = "RECOVERED"
    else:
        outcome = "HEALTHY"
    return {
        "scenario": scenario,
        "outcome": outcome,
        "mission_state_before_shutdown": observed_state,
        "recovery_count": observed_recoveries,
        "packets": observed_packets,
        "events": observed_events,
        "observations": snapshots,
        "public_data_directory": str((root / "dashboard-data").relative_to(output_root)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("runtime") / "reliability-report.json",
        help="Ignored local report path (default: runtime/reliability-report.json)",
    )
    parser.add_argument("--iterations", type=int, default=8)
    parser.add_argument("--stall-after", type=int, default=2)
    parser.add_argument("--max-recoveries", type=int, default=1)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be at least one")

    output_path = args.output
    output_root = output_path.parent / "reliability-runs"
    results = [run_scenario(scenario, output_root, args) for scenario in SUPPORTED_SCENARIOS]
    report = {
        "schema_version": "1.0",
        "mode": "local-reliability-report",
        "scenarios": results,
        "note": "Synthetic worker evidence only; no pool, wallet, revenue, or external work is connected.",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(as_jsonable(report), indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
