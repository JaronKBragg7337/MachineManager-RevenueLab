from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from revenue_lab.ledger import EventLedger
from revenue_lab.economics import assess_reserve, reconcile_reserve
from revenue_lab.models import EventRecord, FinanceSnapshot, VisibilityMode, as_jsonable, utc_now
from revenue_lab.privacy import project_finance, sanitize_snapshot, validate_public_payload
from revenue_lab.preview import build_preview_snapshot
from revenue_lab.publisher import publish_snapshot
from revenue_lab.runtime import RevenueLabRuntime
from revenue_lab.state import transition
from revenue_lab.workers import BitcoinSha256dStratumSpec


class PublicProjectionTests(unittest.TestCase):
    def test_preview_is_explicitly_not_live(self) -> None:
        snapshot = build_preview_snapshot()
        self.assertEqual(snapshot.mode, "design-preview")
        self.assertEqual(snapshot.status, "DESIGN_PREVIEW")
        self.assertEqual(snapshot.worker.state, "NOT_CONNECTED")
        self.assertEqual(snapshot.machine.gpu_utilization_pct, None)

    def test_preview_projection_contains_no_machine_identity_or_command(self) -> None:
        payload = sanitize_snapshot(build_preview_snapshot())
        serialized = json.dumps(payload)
        self.assertNotIn("C:\\", serialized)
        self.assertNotIn("--password", serialized)
        self.assertNotIn("pid", serialized.lower())

    def test_public_exact_keeps_public_address_but_no_secret_fields(self) -> None:
        finance = FinanceSnapshot(
            visibility=VisibilityMode.PUBLIC_EXACT,
            wallet_public_address="bc1qexamplepublicaddress",
            wallet_balance=0.123456,
        )
        result = project_finance(finance)
        self.assertEqual(result["wallet"]["address"], "bc1qexamplepublicaddress")
        validate_public_payload(result)

    def test_public_rounded_masks_address_and_rounds_amounts(self) -> None:
        finance = FinanceSnapshot(
            visibility=VisibilityMode.PUBLIC_ROUNDED,
            estimated_credit=1.239,
            wallet_public_address="bc1qexamplepublicaddress",
        )
        result = project_finance(finance)
        self.assertEqual(result["estimated_credit"], 1.24)
        self.assertEqual(result["wallet"]["address"], "bc1qex...ddress")

    def test_private_projection_omits_finance_values(self) -> None:
        result = project_finance(FinanceSnapshot(visibility=VisibilityMode.PRIVATE, money_received=9.0))
        self.assertIsNone(result["money_received"])
        self.assertIsNone(result["wallet"])

    def test_sensitive_field_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            validate_public_payload({"events": [{"api_token": "should-never-appear"}]})


class LedgerTests(unittest.TestCase):
    def test_events_round_trip_in_append_order(self) -> None:
        event_a = EventRecord(
            timestamp=utc_now(),
            event_id="event-a",
            objective_id="mission-a",
            job_id="job-a",
            worker_id=None,
            actor="test",
            event_type="started",
        )
        event_b = EventRecord(
            timestamp=utc_now(),
            event_id="event-b",
            objective_id="mission-a",
            job_id="job-a",
            worker_id="worker-a",
            actor="test",
            event_type="progress",
            metrics={"rate": 1.0},
        )
        with tempfile.TemporaryDirectory() as directory:
            with EventLedger(Path(directory) / "events.sqlite3") as ledger:
                ledger.append(event_a)
                ledger.append(event_b)
                self.assertEqual(ledger.count(), 2)
                self.assertEqual([event.event_id for event in ledger.recent()], ["event-a", "event-b"])


class PublisherTests(unittest.TestCase):
    def test_publisher_writes_three_valid_json_projections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = publish_snapshot(build_preview_snapshot(), directory)
            self.assertEqual(set(paths), {"latest", "events", "scenarios"})
            for path in paths.values():
                with path.open(encoding="utf-8") as handle:
                    json.load(handle)

    def test_models_are_jsonable(self) -> None:
        self.assertEqual(as_jsonable(VisibilityMode.PUBLIC_EXACT), "public_exact")


class MissionContractTests(unittest.TestCase):
    def test_valid_and_invalid_state_transitions(self) -> None:
        self.assertEqual(transition("PLANNED", "QUEUED").value, "QUEUED")
        with self.assertRaises(ValueError):
            transition("COMPLETE", "RUNNING")

    def test_economic_progress_uses_reserve_not_projection(self) -> None:
        assessment = assess_reserve(20.0, 5.0)
        self.assertEqual(assessment.status, "BUILDING")
        self.assertEqual(assessment.progress_pct, 25.0)
        reconcile_reserve(confirmed_payout=5.0, money_received=5.0, reserve_amount=5.0)
        with self.assertRaises(ValueError):
            reconcile_reserve(confirmed_payout=5.0, money_received=6.0, reserve_amount=6.0)

    def test_bitcoin_lane_is_an_adapter_spec_not_a_manager_identity(self) -> None:
        spec = BitcoinSha256dStratumSpec()
        self.assertEqual(spec.algorithm, "SHA-256d")
        self.assertIn("accepted_shares", spec.required_metrics)
        self.assertNotIn("KeyHunt", spec.adapter_id)

    def test_synthetic_runtime_publishes_real_work_packets_and_closes_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = RevenueLabRuntime(root / "data", root / "state" / "events.sqlite3")
            first = runtime.tick()
            second = runtime.tick()
            runtime.close()
            self.assertEqual(first.mode, "synthetic-demo")
            self.assertEqual(second.worker.state, "RUNNING")
            self.assertEqual(len(second.work_packets), 2)
            self.assertEqual(second.finance.money_received, 0.0)
            with (root / "data" / "latest.json").open(encoding="utf-8") as handle:
                public = json.load(handle)
            self.assertEqual(public["status"], "STOPPED")
            self.assertEqual(public["work_packets"][-1]["state"], "COMPLETE")


if __name__ == "__main__":
    unittest.main()
