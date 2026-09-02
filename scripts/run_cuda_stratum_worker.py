"""Build or run the focused local CUDA + Stratum worker."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "workers" / "cuda_sha256d_worker.cu"
BUILD_DIR = ROOT / "runtime" / "cuda-stratum-worker"
BINARY = BUILD_DIR / "cuda_sha256d_worker.exe"


def find_nvcc() -> Path | None:
    discovered = shutil.which("nvcc")
    if discovered:
        return Path(discovered)
    cuda_path = os.environ.get("CUDA_PATH")
    candidates = []
    if cuda_path:
        candidates.append(Path(cuda_path) / "bin" / "nvcc.exe")
    candidates.extend(
        [
            Path(r"C:\Users\lilli\scoop\apps\cuda\current\bin\nvcc.exe"),
            Path(r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.3\bin\nvcc.exe"),
        ]
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def find_vsdevcmd() -> Path | None:
    candidates = [
        Path(r"C:\Program Files\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat"),
        Path(r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat"),
    ]
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def build() -> int:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    nvcc = find_nvcc()
    if nvcc is None:
        print("nvcc was not found; install or expose the CUDA toolkit first", file=sys.stderr)
        return 69

    if os.name == "nt":
        vsdevcmd = find_vsdevcmd()
        if vsdevcmd is None:
            print("Visual Studio Build Tools VsDevCmd.bat was not found", file=sys.stderr)
            return 69
        command = (
            f'call "{vsdevcmd}" -arch=x64 -host_arch=x64 && '
            f'"{nvcc}" -O3 --std=c++17 -arch=sm_89 "{SOURCE}" -o "{BINARY}"'
        )
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            shell=True,
        )
    else:
        completed = subprocess.run(
            [
                str(nvcc),
                "-O3",
                "--std=c++17",
                "-arch=sm_89",
                str(SOURCE),
                "-o",
                str(BINARY),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    if completed.returncode != 0:
        if completed.stdout:
            print(completed.stdout, file=sys.stderr, end="")
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
        return completed.returncode
    print(f"built {BINARY.relative_to(ROOT)}")
    return 0


def run_worker(args: argparse.Namespace) -> int:
    command = [
        str(BINARY),
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--worker",
        args.worker,
        "--max-shares",
        str(args.max_shares),
        "--seconds",
        str(args.seconds),
        "--batch-nonces",
        str(args.batch_nonces),
        "--threads",
        str(args.threads),
        "--device",
        str(args.device),
    ]
    if args.password_file:
        command.extend(["--password-file", str(args.password_file)])
    elif args.password is not None:
        command.extend(["--password", args.password])
    if args.progress_file:
        command.extend(["--progress-file", str(args.progress_file)])

    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="")
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="compile the worker and exit")
    parser.add_argument("--skip-build", action="store_true", help="use the existing ignored worker binary")
    parser.add_argument("--host", help="Stratum host; required when running")
    parser.add_argument("--port", type=int, help="Stratum TCP port; required when running")
    parser.add_argument("--worker", default="revenue-lab-worker", help="Stratum worker name")
    password_group = parser.add_mutually_exclusive_group()
    password_group.add_argument("--password", help="password for a local test only; do not put production credentials in shell history")
    password_group.add_argument("--password-file", type=Path, help="ignored local file containing the worker password")
    parser.add_argument("--progress-file", type=Path, help="ignored local aggregate progress JSON path")
    parser.add_argument("--max-shares", type=int, default=1, help="stop after this many accepted shares; 0 means no share bound")
    parser.add_argument("--seconds", type=int, default=0, help="stop after this many seconds; 0 means no time bound")
    parser.add_argument("--batch-nonces", type=int, default=1 << 20)
    parser.add_argument("--threads", type=int, default=256)
    parser.add_argument("--device", type=int, default=0)
    args = parser.parse_args()

    if args.build and args.skip_build:
        parser.error("--build and --skip-build cannot be used together")
    if args.max_shares < 0 or args.seconds < 0 or args.batch_nonces <= 0 or args.batch_nonces > 0xFFFFFFFF:
        parser.error("bounds must be non-negative and batch-nonces must fit in uint32")
    if not 1 <= args.threads <= 1024:
        parser.error("--threads must be between 1 and 1024")
    if args.device < 0:
        parser.error("--device must be non-negative")
    if args.build:
        return build()
    if args.host is None or args.port is None or not 1 <= args.port <= 65535:
        parser.error("--host and a valid --port are required when running")
    if not args.skip_build:
        result = build()
        if result != 0:
            return result
    elif not BINARY.is_file():
        print(f"worker binary does not exist: {BINARY}", file=sys.stderr)
        return 66
    return run_worker(args)


if __name__ == "__main__":
    raise SystemExit(main())
