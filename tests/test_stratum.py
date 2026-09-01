from __future__ import annotations

import hashlib
import unittest

from revenue_lab.stratum import (
    StratumJob,
    StratumProtocolError,
    build_coinbase,
    build_header,
    build_merkle_root,
    build_submit_params,
    double_sha256,
    encode_request,
    hash_meets_target,
    parse_json_line,
    target_from_compact,
)


class StratumProtocolTests(unittest.TestCase):
    def make_job(self, *, branches: list[str] | None = None) -> StratumJob:
        return StratumJob.from_notify(
            [
                "job-1",
                "00" * 32,
                "aa",
                "dd",
                branches or [],
                "20000000",
                "1d00ffff",
                "5f5e1000",
                True,
            ]
        )

    def test_json_request_round_trip_is_compact_and_line_delimited(self) -> None:
        line = encode_request("mining.subscribe", ["machine-manager/0.1"], 7)
        self.assertTrue(line.endswith("\n"))
        self.assertNotIn(" ", line)
        self.assertEqual(
            parse_json_line(line),
            {"id": 7, "method": "mining.subscribe", "params": ["machine-manager/0.1"]},
        )
        self.assertEqual(parse_json_line(line.encode("utf-8"))["id"], 7)

    def test_invalid_json_errors_do_not_echo_input(self) -> None:
        with self.assertRaisesRegex(StratumProtocolError, "invalid JSON line") as context:
            parse_json_line('{"secret":"do-not-echo"')
        self.assertNotIn("do-not-echo", str(context.exception))

    def test_notify_is_strictly_validated(self) -> None:
        job = self.make_job(branches=["11" * 32])
        self.assertEqual(job.job_id, "job-1")
        self.assertEqual(job.prevhash_hex, "00" * 32)
        self.assertEqual(job.merkle_branch, (bytes.fromhex("11" * 32),))
        self.assertTrue(job.clean_jobs)

        with self.assertRaises(StratumProtocolError):
            StratumJob.from_notify(["too-short"])
        with self.assertRaises(StratumProtocolError):
            StratumJob.from_notify(
                ["job-1", "not-hex", "aa", "dd", [], "20000000", "1d00ffff", "5f5e1000", True]
            )
        with self.assertRaises(StratumProtocolError):
            StratumJob.from_notify(
                ["job-1", "00" * 32, "aa", "dd", [], "20000000", "1d00ffff", "5f5e1000", 1]
            )

    def test_coinbase_and_merkle_root_match_hashlib(self) -> None:
        job = self.make_job(branches=["11" * 32, "22" * 32])
        coinbase = build_coinbase(job, "bb", "cc")
        self.assertEqual(coinbase, bytes.fromhex("aabbccdd"))
        expected = hashlib.sha256(hashlib.sha256(coinbase).digest()).digest()
        expected = hashlib.sha256(hashlib.sha256(expected + bytes.fromhex("11" * 32)).digest()).digest()
        expected = hashlib.sha256(hashlib.sha256(expected + bytes.fromhex("22" * 32)).digest()).digest()
        self.assertEqual(build_merkle_root(job, "bb", "cc"), expected)

    def test_header_is_80_bytes_with_little_endian_fields(self) -> None:
        job = self.make_job()
        header = build_header(job, "bb", "cc", 0x01020304)
        self.assertEqual(len(header), 80)
        self.assertEqual(header[:4], bytes.fromhex("00000020"))
        self.assertEqual(header[36:68], build_merkle_root(job, "bb", "cc"))
        self.assertEqual(header[68:72], bytes.fromhex("00105e5f"))
        self.assertEqual(header[72:76], bytes.fromhex("ffff001d"))
        self.assertEqual(header[76:], bytes.fromhex("04030201"))

    def test_submit_params_match_header_serialization(self) -> None:
        params = build_submit_params("worker.example", self.make_job(), "cc", 0x01020304)
        self.assertEqual(params, ["worker.example", "job-1", "cc", "5f5e1000", "04030201"])

    def test_genesis_known_vector_passes_network_target(self) -> None:
        genesis_header = bytes.fromhex(
            "01000000"
            + "00" * 32
            + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
            + "29ab5f49"
            + "ffff001d"
            + "1dac2b7c"
        )
        digest = double_sha256(genesis_header)
        self.assertEqual(digest.hex(), "6fe28c0ab6f1b372c1a6a246ae63f74f931e8365e15a089c68d6190000000000")
        target = target_from_compact("1d00ffff")
        self.assertTrue(hash_meets_target(digest, target))
        self.assertFalse(hash_meets_target(b"\xff" * 32, target))

    def test_compact_target_rejects_signed_zero_and_overflow_values(self) -> None:
        self.assertEqual(target_from_compact("1d00ffff"), 0xFFFF << (8 * (0x1D - 3)))
        with self.assertRaises(StratumProtocolError):
            target_from_compact("1d80ffff")
        with self.assertRaises(StratumProtocolError):
            target_from_compact("01000001")
        with self.assertRaises(StratumProtocolError):
            target_from_compact("23010000")

    def test_protocol_helpers_reject_wrong_types(self) -> None:
        with self.assertRaises(StratumProtocolError):
            encode_request("mining.submit", {"not": "a list"}, 1)  # type: ignore[arg-type]
        with self.assertRaises(StratumProtocolError):
            parse_json_line([])  # type: ignore[arg-type]
        with self.assertRaises(StratumProtocolError):
            build_header(self.make_job(), "bb", "cc", -1)


if __name__ == "__main__":
    unittest.main()
