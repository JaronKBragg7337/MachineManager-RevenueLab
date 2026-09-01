# Local CUDA SHA-256d benchmark

This checkpoint adds a small local benchmark for the first Bitcoin worker lane.
It is intentionally not a miner: it does not connect to a pool, create or read a
wallet, submit shares, or make a revenue claim.

## What it verifies

The CUDA kernel constructs an 80-byte serialized Bitcoin block header, varies the
four-byte little-endian nonce, and computes:

```text
SHA-256(SHA-256(header))
```

Before timing work, it hashes the Bitcoin genesis header and compares the result
with the known raw digest:

```text
6fe28c0ab6f1b372c1a6a246ae63f74f931e8365e15a089c68d6190000000000
```

The known-vector check is a correctness gate. A mismatching kernel exits without
reporting a throughput result.

## Run it on Windows

The MSI needs the CUDA toolkit and Visual Studio Build Tools. The checked-in
runner discovers the local `nvcc` installation, loads the Visual Studio developer
environment, compiles for the RTX 4060's `sm_89` architecture, and runs a bounded
deterministic batch:

```powershell
python scripts/run_cuda_benchmark.py --hashes 5000000
```

To change the batch size or CUDA block width:

```powershell
python scripts/run_cuda_benchmark.py --hashes 10000000 --threads 256
```

Build output is kept under ignored `runtime/cuda-benchmark/`. Use
`--skip-build` only when repeating the exact current binary:

```powershell
python scripts/run_cuda_benchmark.py --skip-build --hashes 5000000
```

## Reading the result

The JSON result includes the device, known-vector status, attempted hashes,
elapsed GPU time, and raw `hashrate_hs`. It also includes:

- `network: "none"` — no external service was contacted;
- `revenue_claim: false` — this is not pool accounting or earned money;
- a checksum that keeps the timed work observable to the host.

This rate is a local SHA-256d kernel benchmark, not a production pool miner
rate. A real Bitcoin worker still needs a selectable Stratum implementation,
fresh pool jobs, header/target handling, share validation, submission, and
accounting. That adapter will be connected only after its protocol and receiving
configuration are chosen explicitly.
