"""Run the native CUDA worker through MissionManager against the loopback mock."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from revenue_lab.manager import ManagerPolicy, MissionManager
from revenue_lab.mock_stratum import MockStratumServer, MockStratumSession
from revenue_lab.models import AgentSnapshot, FinanceSnapshot, Mission, MissionState, VisibilityMode
from revenue_lab.probes import sample_nvidia
from revenue_lab.process_worker import ProcessWorkerAdapter, ProcessWorkerSpec
from revenue_lab.stratum import StratumJob


WORKER_RUNNER = PROJECT_ROOT / "scripts" / "run_cuda_stratum_worker.py"


def make_job() -> StratumJob:
    return StratumJob.from_notify(
        [
            "managed-local-job",
            "00" * 32,
            "aa",
            "dd",
            [],
            "20000000",
            "207fffff",
            "5f5e1000",
            True,
        ]
    )


def build_manager(root: Path, host: str, port: int, progress_file: Path) -> MissionManager:
    mission = Mission(
        mission_id="btc-managed-loopback",
        name="Managed CUDA worker acceptance",
        objective="Verify that the native SHA-256d worker produces independently accepted Stratum work.",
        lane="bitcoin",
        state=MissionState.PLANNED,
        success_measure="The loopback endpoint independently accepts a submitted share and the manager records fresh progress.",
        target_amount=20.0,
        target_currency="USD",
        reference_id="ref-local-cuda-worker",
    )
    worker_id = "managed-offline-cuda"
    worker = ProcessWorkerAdapter(
        ProcessWorkerSpec(
            worker_id=worker_id,
            worker_type="Native CUDA SHA-256d Stratum worker",
            executable=sys.executable,
            arguments=(
                str(WORKER_RUNNER),
                "--skip-build",
                "--host",
                host,
                "--port",
                str(port),
                "--worker",
                worker_id,
                "--password",
                "offline-test",
                "--max-shares",
                "1",
                "--batch-nonces",
                "65536",
                "--threads",
                "256",
                "--progress-file",
                str(progress_file),
            ),
            progress_file=progress_file,
            working_directory=PROJECT_ROOT,
        )
    )
    agents = [
        AgentSnapshot(
            agent_id="manager-core",
            role="Mission manager",
            provider="local runtime",
            model="manager-controller",
            state="READY",
            current_action="Preparing the native worker acceptance run.",
            capability_basis="tested_contract",
        ),
        AgentSnapshot(
            agent_id="evidence-steward",
            role="Evidence steward",
            provider="local runtime",
            model="sanitizer",
            state="READY",
            current_action="Waiting for independently verified worker evidence.",
            capability_basis="tested_contract",
        ),
    ]
    return MissionManager(
        mission,
        worker,
        agents,
        root / "dashboard-data",
        root / "events.sqlite3",
        finance=FinanceSnapshot(
            visibility=VisibilityMode.PRIVATE,
            target_amount=20.0,
            note="Loopback acceptance only; no live pool, wallet, or revenue is connected.",
        ),
        machine_sampler=sample_nvidia,
        references=[
            {
                "reference_id": "ref-local-cuda-worker",
                "title": "Native CUDA worker acceptance contract",
                "kind": "local_test",
                "source": "loopback mock",
                "status": "active",
            }
        ],
        scenarios=[
            {
                "scenario_id": "bitcoin-worker-loopback-001",
                "category": "worker_integration",
                "status": "RUNNING",
                "result": "Native CUDA worker evidence is being checked against the loopback verifier.",
                "source": "local integration runtime",
            }
        ],
        policy=ManagerPolicy(stall_after_observations=8, max_recoveries=1),
        job_id="job-btc-managed-loopback",
        mode="managed-local-worker",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true", help="reuse the existing ignored native worker binary")
    parser.add_argument("--ticks", type=int, default=30, help="maximum manager observations")
    parser.add_argument("--interval", type=float, default=0.25, help="seconds between manager observations")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "runtime" / "managed-cuda-worker",
        help="ignored local runtime directory",
    )
    args = parser.parse_args()
    if args.ticks < 1 or args.interval < 0:
        parser.error("--ticks must be positive and --interval cannot be negative")

    if not args.skip_build:
        built = subprocess.run([sys.executable, str(WORKER_RUNNER), "--build"], cwd=PROJECT_ROOT, check=False)
        if built.returncode != 0:
            return built.returncode

    args.output.mkdir(parents=True, exist_ok=True)
    progress_file = args.output / "worker-progress.json"
    if progress_file.exists():
        progress_file.unlink()
    session = MockStratumSession(make_job(), extranonce1="01020304", extranonce2_size=2)
    with MockStratumServer(session) as server:
        host, port = server.address
        manager = build_manager(args.output, host, port, progress_file)
        snapshots = []
        try:
            manager.start()
            time.sleep(1.0)
            for _ in range(args.ticks):
                snapshot = manager.tick()
                snapshots.append(snapshot)
                if snapshot.mission.state in {MissionState.COMPLETE, MissionState.ESCALATED}:
                    break
                if args.interval:
                    time.sleep(args.interval)
            final = snapshots[-1] if snapshots else manager._publish()
        finally:
            manager.close()

    if final.mission.state != MissionState.COMPLETE or len(session.submissions) != 1:
        print("managed native worker acceptance failed", file=sys.stderr)
        return 2
    result = {
        "mode": "managed-local-worker",
        "mission_state": final.mission.state.value,
        "worker_state": final.worker.state if final.worker else None,
        "manager_observations": len(snapshots),
        "work_packets": len(final.work_packets),
        "events": len(final.events),
        "hashes_attempted": final.worker.hashes_attempted if final.worker else None,
        "best_share_difficulty": final.worker.best_share_difficulty if final.worker else None,
        "accepted_shares": final.worker.accepted_shares if final.worker else None,
        "rejected_shares": final.worker.rejected_shares if final.worker else None,
        "loopback_submissions": len(session.submissions),
        "machine_evidence": final.machine.evidence_quality,
        "note": "MissionManager recorded fresh native CUDA progress and an independently accepted loopback share; no pool or revenue was connected.",
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
