from __future__ import annotations

import socket
import unittest

from revenue_lab.mock_stratum import MockStratumServer, MockStratumSession
from revenue_lab.stratum import (
    StratumJob,
    build_header,
    build_submit_params,
    double_sha256,
    encode_request,
    hash_meets_target,
    parse_json_line,
    target_from_compact,
)


class MockStratumTests(unittest.TestCase):
    def make_job(self) -> StratumJob:
        return StratumJob.from_notify(
            [
                "mock-job",
                "00" * 32,
                "aa",
                "dd",
                [],
                "20000000",
                "207fffff",
                "5f5e1000",
                True,
            ]
        )

    def read_message(self, stream) -> dict:
        return parse_json_line(stream.readline())

    def test_loopback_sequence_accepts_an_independently_verified_share(self) -> None:
        session = MockStratumSession(self.make_job(), extranonce1="01020304", extranonce2_size=2)
        with MockStratumServer(session) as server:
            with socket.create_connection(server.address, timeout=2) as connection:
                stream = connection.makefile("rwb")

                stream.write(encode_request("mining.subscribe", [], 1).encode("utf-8"))
                stream.flush()
                subscribe = self.read_message(stream)
                self.assertEqual(subscribe["result"][1:], ["01020304", 2])

                stream.write(encode_request("mining.authorize", ["worker.example", "offline-test"], 2).encode("utf-8"))
                stream.flush()
                self.assertTrue(self.read_message(stream)["result"])
                notification = self.read_message(stream)
                job = StratumJob.from_notify(notification["params"])

                extranonce2 = "beef"
                target = target_from_compact(job.nbits_hex)
                valid_nonce = next(
                    nonce
                    for nonce in range(100)
                    if hash_meets_target(
                        double_sha256(build_header(job, "01020304", extranonce2, nonce)),
                        target,
                    )
                )
                submit = build_submit_params("worker.example", job, extranonce2, valid_nonce)
                stream.write(encode_request("mining.submit", submit, 3).encode("utf-8"))
                stream.flush()
                self.assertTrue(self.read_message(stream)["result"])
                stream.close()

        self.assertEqual(len(session.submissions), 1)
        self.assertEqual(session.submissions[0].nonce, valid_nonce)
        self.assertEqual(session.submissions[0].extranonce2, extranonce2)

    def test_mock_rejects_wrong_job_and_unauthorized_submission(self) -> None:
        session = MockStratumSession(self.make_job(), extranonce2_size=2)
        unauthorized = session.handle_request(
            {"id": 1, "method": "mining.submit", "params": ["worker", "mock-job", "beef", "5f5e1000", "00000000"]}
        )
        self.assertFalse(unauthorized["result"])
        self.assertEqual(unauthorized["error"][0], 24)

        session.handle_request({"id": 2, "method": "mining.subscribe", "params": []})
        session.handle_request({"id": 3, "method": "mining.authorize", "params": ["worker", "test"]})
        wrong_job = session.handle_request(
            {"id": 4, "method": "mining.submit", "params": ["worker", "not-the-job", "beef", "5f5e1000", "00000000"]}
        )
        self.assertFalse(wrong_job["result"])
        self.assertEqual(wrong_job["error"][0], 21)

    def test_mock_does_not_echo_malformed_protocol_data(self) -> None:
        session = MockStratumSession(self.make_job())
        response = session.handle_request(
            {"id": 1, "method": "mining.authorize", "params": ["worker", "do-not-echo"]}
        )
        self.assertNotIn("do-not-echo", str(response))


if __name__ == "__main__":
    unittest.main()
