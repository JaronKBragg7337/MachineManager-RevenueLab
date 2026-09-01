"""Pure Bitcoin Stratum V1 primitives for an offline-tested worker adapter.

This module deliberately does not open sockets, read credentials, or submit
shares. It owns only the protocol representations and deterministic Bitcoin
work calculations that a future worker can call after its transport layer has
been separately reviewed.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Sequence


class StratumProtocolError(ValueError):
    """The message or deterministic work data did not satisfy the contract."""


_HEX_RE = re.compile(r"^[0-9a-fA-F]*$")
_MAX_UINT256 = (1 << 256) - 1


def _hex_bytes(value: Any, field: str, *, length: int | None = None) -> bytes:
    if not isinstance(value, str) or not value or value != value.strip():
        raise StratumProtocolError(f"invalid {field}")
    if len(value) % 2 or not _HEX_RE.fullmatch(value):
        raise StratumProtocolError(f"invalid {field}")
    if length is not None and len(value) != length:
        raise StratumProtocolError(f"invalid {field}")
    try:
        return bytes.fromhex(value)
    except ValueError as error:
        raise StratumProtocolError(f"invalid {field}") from error


def _optional_hex_bytes(value: Any, field: str) -> bytes:
    if value == "":
        return b""
    return _hex_bytes(value, field)


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise StratumProtocolError(f"invalid {field}")
    return value


def parse_json_line(line: str | bytes) -> dict[str, Any]:
    """Parse one JSON-RPC line without exposing malformed input in errors."""

    if isinstance(line, bytes):
        try:
            text = line.decode("utf-8")
        except UnicodeDecodeError as error:
            raise StratumProtocolError("invalid JSON line") from error
    elif isinstance(line, str):
        text = line
    else:
        raise StratumProtocolError("invalid JSON line")

    if not text.strip():
        raise StratumProtocolError("empty JSON line")
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError) as error:
        raise StratumProtocolError("invalid JSON line") from error
    if not isinstance(payload, dict):
        raise StratumProtocolError("JSON line must be an object")
    return payload


def encode_request(method: str, params: Sequence[Any], request_id: int | str) -> str:
    """Encode one compact newline-delimited Stratum request."""

    if not isinstance(method, str) or not method or method != method.strip():
        raise StratumProtocolError("invalid method")
    if not isinstance(params, (list, tuple)):
        raise StratumProtocolError("params must be a sequence")
    if isinstance(request_id, bool) or not isinstance(request_id, (int, str)):
        raise StratumProtocolError("invalid request id")
    if isinstance(request_id, str) and (not request_id or request_id != request_id.strip()):
        raise StratumProtocolError("invalid request id")
    return (
        json.dumps(
            {"id": request_id, "method": method, "params": list(params)},
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    )


@dataclass(frozen=True, slots=True)
class StratumJob:
    """Validated fields from a Stratum ``mining.notify`` message.

    Hex strings retain the pool's display representation. The byte fields are
    decoded once so header construction cannot accidentally concatenate text or
    silently accept malformed hex.
    """

    job_id: str
    prevhash_hex: str
    coinbase1: bytes
    coinbase2: bytes
    merkle_branch: tuple[bytes, ...]
    version_hex: str
    nbits_hex: str
    ntime_hex: str
    clean_jobs: bool

    @classmethod
    def from_notify(cls, params: Sequence[Any]) -> "StratumJob":
        """Validate the standard nine-parameter ``mining.notify`` payload."""

        if not isinstance(params, (list, tuple)) or len(params) != 9:
            raise StratumProtocolError("invalid mining.notify parameters")

        job_id = _require_text(params[0], "job id")
        prevhash = _hex_bytes(params[1], "previous hash", length=64)
        coinbase1 = _optional_hex_bytes(params[2], "coinbase prefix")
        coinbase2 = _optional_hex_bytes(params[3], "coinbase suffix")
        branches = params[4]
        if not isinstance(branches, (list, tuple)):
            raise StratumProtocolError("invalid merkle branches")
        merkle_branch: list[bytes] = []
        for branch in branches:
            merkle_branch.append(_hex_bytes(branch, "merkle branch", length=64))

        version = _hex_bytes(params[5], "version", length=8)
        nbits = _hex_bytes(params[6], "compact target", length=8)
        ntime = _hex_bytes(params[7], "network time", length=8)
        clean_jobs = params[8]
        if not isinstance(clean_jobs, bool):
            raise StratumProtocolError("invalid clean jobs flag")

        return cls(
            job_id=job_id,
            prevhash_hex=prevhash.hex(),
            coinbase1=coinbase1,
            coinbase2=coinbase2,
            merkle_branch=tuple(merkle_branch),
            version_hex=version.hex(),
            nbits_hex=nbits.hex(),
            ntime_hex=ntime.hex(),
            clean_jobs=clean_jobs,
        )


def double_sha256(data: bytes | bytearray | memoryview) -> bytes:
    """Return Bitcoin's SHA-256(SHA-256(data)) digest bytes."""

    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise StratumProtocolError("hash input must be bytes")
    return hashlib.sha256(hashlib.sha256(bytes(data)).digest()).digest()


def build_coinbase(
    job: StratumJob,
    extranonce1: str,
    extranonce2: str,
) -> bytes:
    """Assemble a coinbase transaction from a validated job and extranonces."""

    if not isinstance(job, StratumJob):
        raise StratumProtocolError("invalid Stratum job")
    return job.coinbase1 + _optional_hex_bytes(extranonce1, "extranonce1") + _optional_hex_bytes(
        extranonce2, "extranonce2"
    ) + job.coinbase2


def build_merkle_root(job: StratumJob, extranonce1: str, extranonce2: str) -> bytes:
    """Build the serialized merkle-root bytes for a Stratum job."""

    root = double_sha256(build_coinbase(job, extranonce1, extranonce2))
    for branch in job.merkle_branch:
        root = double_sha256(root + branch)
    return root


def _nonce_bytes(nonce: int) -> bytes:
    if isinstance(nonce, bool) or not isinstance(nonce, int) or not 0 <= nonce <= 0xFFFFFFFF:
        raise StratumProtocolError("invalid nonce")
    return nonce.to_bytes(4, "little")


def build_header(
    job: StratumJob,
    extranonce1: str,
    extranonce2: str,
    nonce: int,
    *,
    ntime: str | None = None,
) -> bytes:
    """Build the 80-byte serialized Bitcoin header for one nonce attempt."""

    if not isinstance(job, StratumJob):
        raise StratumProtocolError("invalid Stratum job")
    version = _hex_bytes(job.version_hex, "version", length=8)
    prevhash = _hex_bytes(job.prevhash_hex, "previous hash", length=64)
    ntime_bytes = _hex_bytes(job.ntime_hex if ntime is None else ntime, "network time", length=8)
    nbits = _hex_bytes(job.nbits_hex, "compact target", length=8)
    header = (
        version[::-1]
        + prevhash[::-1]
        + build_merkle_root(job, extranonce1, extranonce2)
        + ntime_bytes[::-1]
        + nbits[::-1]
        + _nonce_bytes(nonce)
    )
    if len(header) != 80:
        raise StratumProtocolError("constructed header has invalid length")
    return header


def target_from_compact(nbits: str | bytes | int) -> int:
    """Decode Bitcoin's compact ``nBits`` target into a positive integer."""

    if isinstance(nbits, str):
        compact_bytes = _hex_bytes(nbits, "compact target", length=8)
        compact = int.from_bytes(compact_bytes, "big")
    elif isinstance(nbits, bytes):
        if len(nbits) != 4:
            raise StratumProtocolError("invalid compact target")
        compact = int.from_bytes(nbits, "big")
    elif isinstance(nbits, int) and not isinstance(nbits, bool):
        compact = nbits
    else:
        raise StratumProtocolError("invalid compact target")

    if not 0 <= compact <= 0xFFFFFFFF:
        raise StratumProtocolError("invalid compact target")
    exponent = compact >> 24
    mantissa = compact & 0x007FFFFF
    if compact & 0x00800000 or mantissa == 0:
        raise StratumProtocolError("invalid compact target")
    if exponent <= 3:
        target = mantissa >> (8 * (3 - exponent))
    else:
        target = mantissa << (8 * (exponent - 3))
    if not 0 < target <= _MAX_UINT256:
        raise StratumProtocolError("invalid compact target")
    return target


def hash_meets_target(raw_digest: bytes, target: int) -> bool:
    """Compare a raw double-SHA256 digest using Bitcoin's uint256 ordering."""

    if not isinstance(raw_digest, bytes) or len(raw_digest) != 32:
        raise StratumProtocolError("invalid hash digest")
    if isinstance(target, bool) or not isinstance(target, int) or not 0 <= target <= _MAX_UINT256:
        raise StratumProtocolError("invalid target")
    return int.from_bytes(raw_digest[::-1], "big") <= target


def build_submit_params(
    worker_name: str,
    job: StratumJob,
    extranonce2: str,
    nonce: int,
    *,
    ntime: str | None = None,
) -> list[str]:
    """Build standard ``mining.submit`` parameters.

    The time is emitted in the job's Stratum hex representation, while the
    nonce is emitted as the serialized four-byte little-endian value. This
    matches the representation used by the audited provisional GBXminer path
    and keeps submit data tied to the exact header that was checked locally.
    """

    if not isinstance(worker_name, str) or not worker_name or worker_name != worker_name.strip():
        raise StratumProtocolError("invalid worker name")
    if not isinstance(job, StratumJob):
        raise StratumProtocolError("invalid Stratum job")
    _nonce = _nonce_bytes(nonce)
    ntime_bytes = _hex_bytes(job.ntime_hex if ntime is None else ntime, "network time", length=8)
    extranonce2_bytes = _optional_hex_bytes(extranonce2, "extranonce2")
    return [
        worker_name,
        job.job_id,
        extranonce2_bytes.hex(),
        ntime_bytes.hex(),
        _nonce.hex(),
    ]
