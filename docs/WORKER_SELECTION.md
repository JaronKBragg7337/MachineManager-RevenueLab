# Bitcoin worker selection

The first mission lane is Bitcoin SHA-256d work, but a manager contract is not
enough to make a pool worker trustworthy. The candidate must be built, checked,
and observed locally before it receives a pool endpoint or a receiving
configuration.

## Current candidates

### Audited reference: GBXminer `develop`

[GBXminer](https://github.com/d0wn3d/gbxminer/tree/develop) remains an audited
reference because its public source advertises CUDA, SHA-256d,
Stratum/GBT, Windows x64, `sm_89` support, and a local monitoring API. The
repository is GPL-3.0. Its SHA-256d host path includes CPU verification after
the CUDA scan, which is useful for an evidence-first adapter.

The source was audited as a read-only external reference at commit
[`98e7d3ea7573`](https://github.com/d0wn3d/gbxminer/commit/98e7d3ea7573578f56cee3d2711ce48f047fbb05).
It has a real [SHA-256d host path](https://github.com/d0wn3d/gbxminer/blob/develop/sha256/sha256d.cu),
a [CUDA implementation](https://github.com/d0wn3d/gbxminer/blob/develop/sha256/cuda_sha256d.cu),
Stratum tests, and API tests.

The first native Windows solution build was not accepted as validation. The
checked-in Visual Studio project imports `CUDA 9.0.props`, while this MSI has a
newer CUDA toolchain. An isolated compatibility pass compiled the CUDA
translation units for `sm_89`, but its final link mixed MSVC CUDA objects with
MinGW C++ host objects and failed on unresolved C++ ABI/template symbols. No
GBXminer binary was adopted or launched against a pool; the complete result is
in the [GBXminer build audit](GBXMINER_BUILD.md).

### Project-owned focused worker

`workers/cuda_sha256d_worker.cu` is now the preferred implementation path for
the first adapter. It is built natively with the installed CUDA/Visual Studio
toolchain, uses the same verified SHA-256d device computation as the benchmark,
implements the initial Stratum V1 handshake and share path, and writes an
allowlisted progress record. `scripts/run_local_cuda_worker.py` verifies one
share against the independent loopback server, while
`scripts/run_managed_cuda_worker.py` verifies the same executable through the
manager and NVIDIA probe.

This is a local acceptance worker, not a live-pool claim. It still needs
endpoint/TLS, job-rotation, pool-specific difficulty, and economic reporting
checks before a real pool is selected.

### Local kernel benchmark

This repository's own
[credential-free CUDA benchmark](CUDA_BENCHMARK.md) is already validated on the
RTX 4060. It proves the SHA-256d computation and measures deterministic nonce
work, but it is not a Stratum client and cannot produce pool credit. It remains
the correctness and performance reference for the eventual adapter.

### Older ccminer lineage

[tpruvot/ccminer](https://github.com/tpruvot/ccminer) is a known CUDA/Stratum
reference with a SHA256d mode, but its public README describes a much older
toolchain and the repository is no longer an attractive first build target for
this Windows/CUDA installation. It remains useful for protocol and historical
comparison, not as the selected live binary.

## Acceptance gates before live work

The selected worker must pass these gates in an isolated local run:

1. Build from a pinned public source revision or this repository's checked-in
   source with no credentials in the build tree. **PASS locally.**
2. Pass a known SHA-256d vector and a bounded offline benchmark. **PASS
   locally.**
3. Complete subscribe, authorize, job-notification, target-comparison, and
   submit behavior against a local mock Stratum server. **PASS locally.**
4. Expose a small allowlisted aggregate report containing fresh work cursor,
   hashrate, accepted shares, rejected shares, pool connection, and uptime.
   **PASS locally.**
5. Let the manager detect a stale report, worker crash, malformed report, and
   false process-only liveness signal. **PASS with synthetic reliability
   workers; native manager path passes bounded completion.**
6. Keep the worker's local API bound to loopback and prevent raw command lines,
   credentials, private keys, seeds, or unrestricted worker output from entering
   the public projection. **PASS for the current local acceptance path.**

The remaining live gates are endpoint/TLS behavior, pool-specific difficulty and
job rotation, long-running resource observation, receiving reconciliation, and
economic reporting. No live pool is configured at this checkpoint.

Only after those gates pass will a separately chosen pool and receiving
configuration be connected. That later configuration belongs in ignored local
runtime state, never in this public repository.

## Protocol reference

The [Bitcoin Developer Guide's mining section](https://developer.bitcoin.org/devguide/mining.html)
describes block-header proof of work and pooled shares. The
[Stratum mining protocol specification](https://stratumprotocol.org/specification/05-mining-protocol/)
describes job distribution and share submission. These protocol references are
why the dashboard will show actual jobs, shares, and receipts rather than
invented AI “phrases.”
