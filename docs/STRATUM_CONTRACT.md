# Offline Stratum contract

The first live mission lane will use Bitcoin SHA-256d work distributed by a
pool or a local solo endpoint. Before any endpoint or receiving configuration
is connected, the deterministic protocol layer must pass an offline contract.

`revenue_lab/stratum.py` is intentionally transport-free. It does not open a
socket, read a credential, or submit a share. It validates and provides the
small operations that a separately reviewed transport/worker can use:

- compact JSON-RPC request encoding and line parsing;
- strict `mining.notify` job validation;
- coinbase and merkle-root construction;
- serialized 80-byte header construction;
- Bitcoin compact-target decoding and uint256 digest comparison;
- `mining.submit` parameter construction tied to the serialized header.

The module rejects malformed fields without echoing raw protocol input. The
tests use the Bitcoin genesis header as a known vector and independently check
coinbase, merkle, endian, target, and submit representations.

## Message boundary

The eventual adapter will implement the normal Stratum V1 sequence against a
local mock first:

```text
mining.subscribe
        -> subscription result and extranonce assignment
mining.authorize
        -> authorization result
mining.notify
        -> validated job
header construction + SHA-256d scan
        -> local target/share check
mining.submit
        -> accepted or rejected response
```

The current contract does not claim a pool connection or revenue. It is a
correctness layer for the future worker, not a live miner.

`revenue_lab/mock_stratum.py` now provides the next local gate: a loopback-only
TCP session with no external bind and no credentials. It runs the request
sequence, sends a validated mock job, reconstructs each submitted header, and
accepts a share only when its digest meets the mock compact target. The test
does not contact a pool or create economic credit.

## Representation rule

`version`, `prevhash`, `ntime`, and `nbits` arrive as Stratum hex fields. Header
construction reverses the serialized 32-bit and previous-block fields where
Bitcoin requires little-endian wire order, keeps the computed merkle root in
its serialized digest-byte order, and appends the nonce as a four-byte
little-endian integer. Submit parameters retain the job-provided time hex and
use the serialized little-endian nonce bytes so the submitted work identifies
the header that was actually checked.

## Next acceptance gate

The next implementation step is to connect a pinned external worker to this
same local mock and compare its progress report with the manager's allowlisted
worker contract. Only after that passes should the worker receive a real
endpoint or local receiving configuration.
