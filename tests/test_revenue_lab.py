from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from revenue_lab.ledger import EventLedger
from revenue_lab.economics import assess_reserve, reconcile_reserve
from revenue_lab.manager import ManagerPolicy, MissionManager
from revenue_lab.models import (
    AgentSnapshot,
    EventRecord,
    FinanceSnapshot,
    Mission,
    MissionState,
    ReceiptRecord,
    VisibilityMode,
    as_jsonable,
    utc_now,
)
from revenue_lab.privacy import project_finance, sanitize_snapshot, validate_public_payload
from revenue_lab.preview import build_preview_snapshot
from revenue_lab.publisher import publish_snapshot
from revenue_lab.runtime import RevenueLabRuntime
from revenue_lab.progress import ProgressParseError, parse_progress
from revenue_lab.probes import parse_nvidia_csv
from revenue_lab.process_worker import ProcessWorkerAdapter, ProcessWorkerSpec
from revenue_lab.finance import can_propose_return, classify_receipt, mark_return_proposed
from revenue_lab.state import transition
from revenue_lab.synthetic import ScenarioWorker
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

    def test_progress_parser_keeps_aggregate_fields_and_ignores_unknown_fields(self) -> None:
        observation = parse_progress(
            {
                "worker_id": "btc-worker-001",
                "state": "RUNNING",
                "progress_cursor": "job-42",
                "rate": 2.1,
                "rate_unit": "GH/s",
                "accepted_shares": 7,
                "rejected_shares": 1,
                "pool_connected": True,
                "raw_log_line": "not included",
            }
        )
        self.assertEqual(observation.metrics["accepted_shares"], 7)
        self.assertNotIn("raw_log_line", observation.metrics)
        with self.assertRaises(ProgressParseError):
            parse_progress({"worker_id": "btc-worker-001"})

    def test_nvidia_probe_parser_converts_memory_and_chooses_active_gpu(self) -> None:
        snapshot = parse_nvidia_csv("12,40,15.5,100,2048\n78,61,81.0,2304,8188\n")
        self.assertEqual(snapshot.gpu_utilization_pct, 78.0)
        self.assertEqual(snapshot.vram_used_gb, 2.25)
        self.assertEqual(snapshot.evidence_quality, "nvidia_smi")

    def test_process_adapter_does_not_treat_process_liveness_as_useful_work(self) -> None:
        spec = ProcessWorkerSpec(
            worker_id="btc-worker-001",
            worker_type="Bitcoin SHA-256d adapter",
            executable="worker.exe",
            arguments=("--configured-outside-repo",),
        )
        adapter = ProcessWorkerAdapter(spec)
        self.assertEqual(spec.command[0], "worker.exe")
        self.assertEqual(adapter.observe().evidence_quality, "not_started")

    def test_unrecognized_confirmed_receipt_requires_a_separate_return_proposal(self) -> None:
        receipt = ReceiptRecord(
            receipt_id="receipt-001",
            asset="BTC",
            amount=0.001,
            txid="a" * 64,
            confirmations=1,
            classification=classify_receipt(expected=False, confirmations=1),
            status="confirmed",
            observed_at=utc_now(),
            source="wallet-observer",
        )
        self.assertTrue(can_propose_return(receipt))
        proposed = mark_return_proposed(receipt)
        self.assertEqual(proposed.classification.value, "return_proposed")
        public = project_finance(FinanceSnapshot(visibility=VisibilityMode.PUBLIC_ROUNDED, receipts=[receipt]))
        self.assertEqual(public["receipts"][0]["txid"], "aaaaaaaa...aaaaaaaa")
        self.assertEqual(public["receipts"][0]["amount"], 0.0)


class ManagerRuntimeTests(unittest.TestCase):
    def _manager(self, root: Path, scenario: str, *, max_recoveries: int = 1) -> MissionManager:
        mission = Mission(
            mission_id=f"mission-{scenario}",
            name=f"Synthetic {scenario}",
            objective="Exercise the manager contract with a deterministic worker.",
            lane="synthetic",
            state=MissionState.PLANNED,
            target_amount=None,
        )
        agents = [
            AgentSnapshot(
                agent_id="manager-core",
                role="Mission manager",
                provider="local runtime",
                model="manager-controller",
                state="READY",
                current_action="Preparing.",
            ),
            AgentSnapshot(
                agent_id="evidence-steward",
                role="Evidence steward",
                provider="local runtime",
                model="sanitizer",
                state="READY",
                current_action="Preparing.",
            ),
        ]
        return MissionManager(
            mission,
            ScenarioWorker(scenario=scenario, worker_id=f"worker-{scenario}"),
            agents,
            root / scenario / "data",
            root / scenario / "events.sqlite3",
            finance=FinanceSnapshot(visibility=VisibilityMode.PRIVATE, target_amount=None),
            policy=ManagerPolicy(stall_after_observations=2, max_recoveries=max_recoveries),
            mode="test-runtime",
        )

    def test_healthy_worker_publishes_fresh_progress_packet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self._manager(Path(directory), "healthy")
            snapshot = manager.tick()
            manager.close()
            self.assertEqual(snapshot.mission.state, MissionState.RUNNING)
            self.assertEqual(snapshot.work_packets[-1].state, "COMPLETE")
            self.assertEqual(snapshot.worker.evidence_quality, "synthetic_observation")
            self.assertGreaterEqual(len(snapshot.events), 5)

    def test_false_liveness_becomes_stall_and_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self._manager(Path(directory), "false_liveness_once")
            manager.tick()
            recovered = manager.tick()
            manager.close()
            self.assertEqual(recovered.mission.state, MissionState.RUNNING)
            self.assertEqual(recovered.worker.recovery_count, 1)
            self.assertTrue(any(event.event_type == "worker_recovery_started" for event in recovered.events))
            self.assertTrue(any(event.new_state == "STALLED" for event in recovered.events))

    def test_crash_recovers_without_executive_intervention(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self._manager(Path(directory), "crash_once")
            recovered = manager.tick()
            manager.close()
            self.assertEqual(recovered.mission.state, MissionState.RUNNING)
            self.assertEqual(recovered.worker.recovery_count, 1)
            self.assertTrue(any(event.new_state == "FAILED" for event in recovered.events))

    def test_repeated_failure_escalates_at_recovery_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self._manager(Path(directory), "repeat_failure", max_recoveries=1)
            manager.tick()
            escalated = manager.tick()
            manager.close()
            self.assertEqual(escalated.mission.state, MissionState.ESCALATED)
            self.assertEqual(escalated.worker.state, "ESCALATED")
            self.assertTrue(any(event.event_type == "manager_escalated" for event in escalated.events))

    def test_new_manager_keeps_prior_sqlite_events_and_uses_new_event_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self._manager(root, "healthy")
            first.tick()
            first.close()
            second = self._manager(root, "healthy")
            snapshot = second.tick()
            second.close()
            self.assertGreater(len(snapshot.events), 1)
            event_ids = [event.event_id for event in snapshot.events]
            self.assertEqual(len(event_ids), len(set(event_ids)))


if __name__ == "__main__":
    unittest.main()
