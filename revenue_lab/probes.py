"""Machine-level evidence probes with a small, public-safe output shape."""

from __future__ import annotations

import csv
import subprocess
from io import StringIO

from .models import MachineSnapshot, utc_now


def _number(value: str) -> float | None:
    cleaned = value.strip()
    if not cleaned or cleaned.upper() in {"N/A", "NA", "NOT SUPPORTED"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_nvidia_csv(output: str) -> MachineSnapshot:
    """Parse only nvidia-smi's numeric query output; discard all other text."""

    rows = []
    for row in csv.reader(StringIO(output)):
        if len(row) < 5:
            continue
        values = [_number(item) for item in row[:5]]
        if any(value is None for value in values):
            continue
        utilization, temperature, power, memory_used, memory_total = values
        rows.append((utilization, temperature, power, memory_used, memory_total))
    if not rows:
        return MachineSnapshot(state="UNAVAILABLE", evidence_quality="probe_unavailable", sampled_at=utc_now())

    utilization, temperature, power, memory_used, memory_total = max(rows, key=lambda item: item[0] or 0)
    return MachineSnapshot(
        state="OBSERVED",
        gpu_utilization_pct=utilization,
        gpu_temperature_c=temperature,
        gpu_power_w=power,
        vram_used_gb=round((memory_used or 0) / 1024, 3),
        vram_total_gb=round((memory_total or 0) / 1024, 3),
        sampled_at=utc_now(),
        evidence_quality="nvidia_smi",
    )


def sample_nvidia(command: str = "nvidia-smi") -> MachineSnapshot:
    """Sample the installed NVIDIA adapter without invoking a shell."""

    query = [
        command,
        "--query-gpu=utilization.gpu,temperature.gpu,power.draw,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(query, capture_output=True, text=True, timeout=5, check=True)
    except (OSError, subprocess.SubprocessError):
        return MachineSnapshot(state="UNAVAILABLE", evidence_quality="probe_unavailable", sampled_at=utc_now())
    return parse_nvidia_csv(result.stdout)

