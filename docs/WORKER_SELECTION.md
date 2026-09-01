# Bitcoin worker selection

The first mission lane is Bitcoin SHA-256d work, but a manager contract is not
enough to make a pool worker trustworthy. The candidate must be built, checked,
and observed locally before it receives a pool endpoint or a receiving
configuration.

## Current candidates

### Primary candidate: GBXminer `develop`

[GBXminer](https://github.com/d0wn3d/gbxminer/tree/develop) is the current
provisional candidate because its public source advertises CUDA, SHA-256d,
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
newer CUDA toolchain. The newer CI route uses an MSYS2/autotools build and
additional Windows link setup, so that route still needs an isolated build
check. No GBXminer binary has been launched against a pool.

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

1. Build from a pinned public source revision with no credentials in the build
   tree.
2. Pass a known SHA-256d vector and a bounded offline benchmark.
3. Complete subscribe, authorize, job-notification, target-comparison, and
   submit behavior against a local mock Stratum server.
4. Expose a small allowlisted aggregate report containing fresh work cursor,
   hashrate, job freshness, accepted shares, rejected shares, and best share
   difficulty.
5. Let the manager detect a stale report, worker crash, malformed report, and
   false process-only liveness signal.
6. Keep the worker's local API bound to loopback and prevent raw command lines,
   credentials, private keys, seeds, or unrestricted worker output from entering
   the public projection.

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
