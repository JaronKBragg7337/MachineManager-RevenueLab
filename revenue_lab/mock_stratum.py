"""Loopback-only Stratum harness for worker acceptance tests.

The server binds to 127.0.0.1, uses no credentials, and accepts no external
connections. It exists to test protocol sequencing and independently rebuild a
submitted header before reporting a share as accepted.
"""

from __future__ import annotations

import json
import socketserver
import threading
from dataclasses import dataclass
from typing import Any

from .stratum import (
    StratumJob,
    StratumProtocolError,
    _hex_bytes,
    build_header,
    double_sha256,
    hash_meets_target,
    parse_json_line,
    target_from_compact,
)


@dataclass(frozen=True, slots=True)
class MockSubmission:
    """Sanitized local record of a share checked by the mock."""

    worker_name: str
    job_id: str
    extranonce2: str
    ntime: str
    nonce: int
    digest_hex: str


def _message_line(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


class MockStratumSession:
    """Stateful in-memory Stratum session used by the loopback server."""

    def __init__(
        self,
        job: StratumJob,
        *,
        extranonce1: str = "01020304",
        extranonce2_size: int = 4,
    ) -> None:
        if not isinstance(job, StratumJob):
            raise StratumProtocolError("invalid mock job")
        if not isinstance(extranonce2_size, int) or isinstance(extranonce2_size, bool):
            raise StratumProtocolError("invalid extranonce size")
        if not 1 <= extranonce2_size <= 16:
            raise StratumProtocolError("invalid extranonce size")
        self.job = job
        self.extranonce1 = _hex_bytes(extranonce1, "extranonce1").hex()
        self.extranonce2_size = extranonce2_size
        self.target = target_from_compact(job.nbits_hex)
        self.subscribed = False
        self.authorized = False
        self._submissions: list[MockSubmission] = []
        self._lock = threading.Lock()

    @property
    def submissions(self) -> tuple[MockSubmission, ...]:
        with self._lock:
            return tuple(self._submissions)

    def notification(self) -> dict[str, Any]:
        """Return the validated job in standard ``mining.notify`` shape."""

        return {
            "id": None,
            "method": "mining.notify",
            "params": [
                self.job.job_id,
                self.job.prevhash_hex,
                self.job.coinbase1.hex(),
                self.job.coinbase2.hex(),
                [branch.hex() for branch in self.job.merkle_branch],
                self.job.version_hex,
                self.job.nbits_hex,
                self.job.ntime_hex,
                self.job.clean_jobs,
            ],
        }

    @staticmethod
    def _request_id(request: dict[str, Any]) -> int | str | None:
        request_id = request.get("id")
        if request_id is None or isinstance(request_id, bool):
            return None
        if isinstance(request_id, (int, str)):
            return request_id
        return None

    def _response(self, request: dict[str, Any], result: Any, error: list[Any] | None = None) -> dict[str, Any]:
        return {"id": self._request_id(request), "result": result, "error": error}

    def _params(self, request: dict[str, Any]) -> list[Any] | None:
        params = request.get("params")
        return params if isinstance(params, list) else None

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle one request without returning raw request data in errors."""

        if not isinstance(request, dict) or not isinstance(request.get("method"), str):
            return {"id": None, "result": None, "error": [-32600, "invalid request", None]}
        method = request["method"]
        params = self._params(request)
        if params is None:
            return self._response(request, None, [-32602, "invalid parameters", None])

        if method == "mining.subscribe":
            self.subscribed = True
            return self._response(
                request,
                [
                    [["mining.set_difficulty", "mock-difficulty"], ["mining.notify", "mock-job"]],
                    self.extranonce1,
                    self.extranonce2_size,
                ],
            )

        if method == "mining.authorize":
            if not self.subscribed or len(params) != 2 or not all(isinstance(item, str) for item in params):
                return self._response(request, False, [24, "unauthorized", None])
            self.authorized = True
            return self._response(request, True)

        if method == "mining.submit":
            return self._handle_submit(request, params)

        return self._response(request, None, [-32601, "method not supported", None])

    def _handle_submit(self, request: dict[str, Any], params: list[Any]) -> dict[str, Any]:
        if not self.authorized:
            return self._response(request, False, [24, "unauthorized", None])
        if len(params) != 5 or not all(isinstance(item, str) for item in params):
            return self._response(request, False, [20, "invalid share", None])

        worker_name, job_id, extranonce2, ntime, nonce_hex = params
        if not worker_name or worker_name != worker_name.strip() or job_id != self.job.job_id:
            return self._response(request, False, [21, "job not found", None])
        try:
            extranonce2_bytes = _hex_bytes(extranonce2, "extranonce2")
            ntime_bytes = _hex_bytes(ntime, "network time", length=8)
            nonce_bytes = _hex_bytes(nonce_hex, "nonce", length=8)
        except StratumProtocolError:
            return self._response(request, False, [20, "invalid share", None])
        if len(extranonce2_bytes) != self.extranonce2_size:
            return self._response(request, False, [20, "invalid share", None])

        nonce = int.from_bytes(nonce_bytes, "little")
        try:
            header = build_header(self.job, self.extranonce1, extranonce2, nonce, ntime=ntime)
        except StratumProtocolError:
            return self._response(request, False, [20, "invalid share", None])
        digest = double_sha256(header)
        if not hash_meets_target(digest, self.target):
            return self._response(request, False, [23, "share rejected", None])

        submission = MockSubmission(
            worker_name=worker_name,
            job_id=job_id,
            extranonce2=extranonce2_bytes.hex(),
            ntime=ntime_bytes.hex(),
            nonce=nonce,
            digest_hex=digest.hex(),
        )
        with self._lock:
            self._submissions.append(submission)
        return self._response(request, True)


class MockStratumServer:
    """A short-lived loopback TCP server for end-to-end adapter tests."""

    def __init__(self, session: MockStratumSession) -> None:
        self.session = session
        self._server: socketserver.ThreadingTCPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        if self._server is None:
            raise RuntimeError("mock Stratum server is not running")
        host, port = self._server.server_address
        return str(host), int(port)

    def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("mock Stratum server is already running")
        session = self.session

        class Handler(socketserver.StreamRequestHandler):
            def handle(self) -> None:
                while True:
                    line = self.rfile.readline()
                    if not line:
                        return
                    try:
                        request = parse_json_line(line)
                    except StratumProtocolError:
                        self.wfile.write(_message_line({"id": None, "result": None, "error": [-32700, "invalid request", None]}))
                        self.wfile.flush()
                        continue
                    response = session.handle_request(request)
                    self.wfile.write(_message_line(response))
                    self.wfile.flush()
                    if request.get("method") == "mining.authorize" and response.get("result") is True:
                        self.wfile.write(_message_line(session.notification()))
                        self.wfile.flush()

        class LoopbackServer(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self._server = LoopbackServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, name="mock-stratum", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is None:
            return
        server = self._server
        thread = self._thread
        self._server = None
        self._thread = None
        server.shutdown()
        server.server_close()
        if thread is not None:
            thread.join(timeout=2)

    def __enter__(self) -> "MockStratumServer":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.stop()
