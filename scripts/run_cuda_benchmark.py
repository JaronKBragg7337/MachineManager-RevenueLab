"""Build and run the local, credential-free CUDA SHA-256d benchmark."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "workers" / "cuda_sha256d_benchmark.cu"
BUILD_DIR = ROOT / "runtime" / "cuda-benchmark"
BINARY = BUILD_DIR / "cuda_sha256d_benchmark.exe"


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
    return 0


def run_benchmark(hashes: int, threads: int) -> int:
    completed = subprocess.run(
        [str(BINARY), str(hashes), str(threads)],
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

    output_lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not output_lines:
        print("benchmark produced no JSON result", file=sys.stderr)
        return 70
    try:
        result = json.loads(output_lines[-1])
    except json.JSONDecodeError as error:
        print(f"benchmark produced invalid JSON: {error}", file=sys.stderr)
        return 70
    print(json.dumps(result, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hashes",
        type=int,
        default=5_000_000,
        help="number of deterministic SHA-256d header attempts (default: 5,000,000)",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=256,
        help="CUDA threads per block (default: 256; maximum: 1024)",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="run the existing ignored runtime binary without recompiling",
    )
    args = parser.parse_args()

    if args.hashes <= 0:
        parser.error("--hashes must be positive")
    if not 1 <= args.threads <= 1024:
        parser.error("--threads must be between 1 and 1024")

    if not args.skip_build:
        result = build()
        if result != 0:
            return result
    elif not BINARY.is_file():
        print(f"benchmark binary does not exist: {BINARY}", file=sys.stderr)
        return 66

    return run_benchmark(args.hashes, args.threads)


if __name__ == "__main__":
    raise SystemExit(main())
