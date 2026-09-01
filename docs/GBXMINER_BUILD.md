# GBXminer build audit

GBXminer was evaluated as a possible first Stratum worker for the Bitcoin
mission lane. It remains a read-only third-party reference, not a dependency
of this repository and not an adopted live worker.

## Pinned source

- Project: [d0wn3d/gbxminer](https://github.com/d0wn3d/gbxminer)
- Revision: [`98e7d3ea7573`](https://github.com/d0wn3d/gbxminer/commit/98e7d3ea7573578f56cee3d2711ce48f047fbb05)
- License: GPL-3.0
- Relevant capabilities audited: CUDA SHA-256d, Stratum/GBT plumbing, Windows
  support, `sm_89` target, and a local monitoring API.

## Build result

The checked-in Visual Studio solution was tried first. It imports the legacy
CUDA 9.0 Visual Studio property sheet, so it cannot build against the CUDA
toolchain installed on the test machine without changing the upstream project
configuration.

An isolated compatibility build was then attempted with the installed CUDA
toolchain and an Ada `sm_89` target. The CUDA translation units compiled,
including the SHA-256d sources, but the final link was not accepted. The
upstream full tree mixes MSVC-produced CUDA C++ objects with MinGW-produced
host C++ objects across multiple algorithm modules. The resulting unresolved
C++ ABI and template symbols mean that a binary produced by that route would
not be trustworthy evidence of a working worker.

No GBXminer executable was adopted or launched. No pool endpoint, worker
credential, wallet configuration, or network mining session was used during
this audit.

## Decision

The project keeps GBXminer as a protocol and implementation reference. The
accepted local evidence is the repository's own credential-free CUDA
SHA-256d benchmark plus the transport-free and loopback Stratum acceptance
harness. A live adapter must pass those gates with a reproducible native build
before any pool configuration is considered.

The next worker implementation should either:

1. use a focused native Windows CUDA worker built from this repository's
   validated SHA-256d kernel and Stratum contract; or
2. use another pinned public worker whose complete build and acceptance path
   passes without a mixed-toolchain ABI boundary.

Until one of those paths passes, the public dashboard must continue to label
the mission as a design preview and must not imply mining credit or revenue.
