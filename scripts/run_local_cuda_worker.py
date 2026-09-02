"""Run the focused CUDA worker against the credential-free loopback Stratum mock."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from revenue_lab.mock_stratum import MockStratumServer, MockStratumSession
from revenue_lab.stratum import StratumJob


WORKER_RUNNER = PROJECT_ROOT / "scripts" / "run_cuda_stratum_worker.py"


def make_job() -> StratumJob:
    return StratumJob.from_notify(
        [
            "local-cuda-job",
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true", help="reuse the existing ignored CUDA worker binary")
    args = parser.parse_args()

    if not args.skip_build:
        built = subprocess.run(
            [sys.executable, str(WORKER_RUNNER), "--build"],
            cwd=PROJECT_ROOT,
            check=False,
        )
        if built.returncode != 0:
            return built.returncode

    session = MockStratumSession(make_job(), extranonce1="01020304", extranonce2_size=2)
    with MockStratumServer(session) as server:
        host, port = server.address
        completed = subprocess.run(
            [
                sys.executable,
                str(WORKER_RUNNER),
                "--skip-build",
                "--host",
                host,
                "--port",
                str(port),
                "--worker",
                "offline-cuda-worker",
                "--password",
                "offline-test",
                "--max-shares",
                "1",
                "--batch-nonces",
                "65536",
                "--threads",
                "256",
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="")
    if completed.returncode != 0:
        if completed.stdout:
            print(completed.stdout, file=sys.stderr, end="")
        return completed.returncode

    progress = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        try:
            progress.append(json.loads(line))
        except json.JSONDecodeError:
            print("worker emitted a non-JSON progress line", file=sys.stderr)
            return 70
    if (
        not progress
        or progress[-1].get("state") != "COMPLETE"
        or progress[-1].get("accepted_shares") != 1
        or progress[-1].get("rejected_shares") != 0
        or len(session.submissions) != 1
    ):
        print("loopback CUDA worker acceptance failed", file=sys.stderr)
        return 2

    result = {
        "mode": "loopback-cuda-worker",
        "worker_exit_code": completed.returncode,
        "progress_packets": len(progress),
        "first_state": progress[0].get("state"),
        "last_state": progress[-1].get("state"),
        "hashes": progress[-1].get("hashes"),
        "best_share_difficulty": progress[-1].get("best_share_difficulty"),
        "accepted_shares": progress[-1].get("accepted_shares"),
        "rejected_shares": progress[-1].get("rejected_shares"),
        "loopback_submissions": len(session.submissions),
        "submitted_nonce": session.submissions[0].nonce,
        "note": "Local CUDA worker accepted a share through the loopback mock; no pool or revenue was connected.",
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
