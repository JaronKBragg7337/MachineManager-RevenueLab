"""Generic external-process worker adapter used by real mission lanes."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from .progress import ProgressParseError, read_progress
from .workers import WorkerObservation


@dataclass(frozen=True, slots=True)
class ProcessWorkerSpec:
    worker_id: str
    worker_type: str
    executable: str
    arguments: tuple[str, ...] = ()
    progress_file: Path | None = None
    working_directory: Path | None = None
    environment: Mapping[str, str] = field(default_factory=dict, repr=False)

    @property
    def command(self) -> list[str]:
        """Return the launch vector without exposing it through public telemetry."""

        return [self.executable, *self.arguments]


class ProcessWorkerAdapter:
    """Supervise a configured worker process without assuming its implementation."""

    def __init__(self, spec: ProcessWorkerSpec):
        self.spec = spec
        self.worker_id = spec.worker_id
        self.worker_type = spec.worker_type
        self.process: subprocess.Popen[bytes] | None = None
        self._objective = ""
        self._resources: dict[str, object] = {}

    def start(self, objective: str, resources: dict[str, object]) -> None:
        if self.process is not None and self.process.poll() is None:
            raise RuntimeError("worker process is already running")
        self._objective = objective
        self._resources = dict(resources)
        environment = os.environ.copy()
        environment.update(self.spec.environment)
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        self.process = subprocess.Popen(
            self.spec.command,
            cwd=self.spec.working_directory,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )

    def observe(self) -> WorkerObservation:
        if self.process is None:
            return WorkerObservation(
                worker_id=self.worker_id,
                state="NOT_CONNECTED",
                progress_cursor=None,
                evidence_quality="not_started",
            )
        if self.process.poll() is not None:
            # A bounded worker may publish its terminal aggregate report and
            # exit in the same moment. Preserve a verified COMPLETE/STOPPED
            # report instead of converting that clean result into a process
            # failure. Any other exited process remains FAILED.
            if self.spec.progress_file is not None:
                try:
                    terminal_observation = read_progress(self.spec.progress_file)
                except ProgressParseError:
                    terminal_observation = None
                if terminal_observation is not None and terminal_observation.state in {"COMPLETE", "STOPPED"}:
                    return terminal_observation
            return WorkerObservation(
                worker_id=self.worker_id,
                state="FAILED",
                progress_cursor=None,
                evidence_quality="process_exit",
                note="The worker process is no longer running.",
            )
        if self.spec.progress_file is None:
            return WorkerObservation(
                worker_id=self.worker_id,
                state="RUNNING",
                progress_cursor=None,
                evidence_quality="process_only",
                note="A progress file is not configured; process liveness is not proof of useful work.",
            )
        if not self.spec.progress_file.is_file():
            return WorkerObservation(
                worker_id=self.worker_id,
                state="STARTING",
                progress_cursor=None,
                evidence_quality="progress_pending",
                note="The worker is running but has not published its first aggregate progress report.",
            )
        try:
            return read_progress(self.spec.progress_file)
        except ProgressParseError:
            return WorkerObservation(
                worker_id=self.worker_id,
                state="STALLED",
                progress_cursor=None,
                evidence_quality="progress_unavailable",
                note="The aggregate progress report is unavailable or malformed.",
            )

    def stop(self, reason: str, timeout_seconds: float = 5.0) -> None:
        del reason
        if self.process is None or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=timeout_seconds)

    def recover(self, reason: str) -> None:
        objective = self._objective
        resources = dict(self._resources)
        self.stop(reason)
        self.start(objective, resources)
