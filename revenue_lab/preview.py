"""Honest design-preview data used before a live worker is connected."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import (
    AgentSnapshot,
    EventRecord,
    FinanceSnapshot,
    MachineSnapshot,
    Mission,
    MissionState,
    PublicSnapshot,
    VisibilityMode,
    WorkPacket,
    WorkerSnapshot,
    utc_now,
)


def build_preview_snapshot() -> PublicSnapshot:
    """Return a truthful, source-labeled snapshot for the initial website build."""

    now = utc_now()
    review_by = (
        datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=30)
    ).isoformat().replace("+00:00", "Z")
    mission = Mission(
        mission_id="btc-pool-experiment",
        name="Bitcoin proof-of-work experiment",
        objective="Measure whether a persistent SHA-256d worker can build verified pool credit toward a subscription reserve.",
        lane="bitcoin",
        state=MissionState.PLANNED,
        success_measure="Confirmed payout and money received are greater than the measured mission-attributed cost.",
        target_amount=20.0,
        target_currency="USD",
        reference_id="ref-first-mission",
    )
    events = [
        EventRecord(
            timestamp=now,
            event_id="preview-foundation-001",
            objective_id=mission.mission_id,
            job_id="job-revenue-lab-foundation",
            worker_id=None,
            actor="revenue-lab-builder",
            event_type="foundation_checkpoint",
            new_state="FOUNDATION_READY",
            action="Defined the interchangeable mission, evidence, finance, and worker contracts.",
            outcome="Ready for adapter implementation; no live mining claim made.",
            artifact_refs=["docs/ARCHITECTURE.md", "revenue_lab/models.py"],
            source="local_build",
            public_summary="Core contracts are ready for a real worker adapter.",
        ),
        EventRecord(
            timestamp=now,
            event_id="preview-dashboard-001",
            objective_id=mission.mission_id,
            job_id="job-revenue-lab-foundation",
            worker_id=None,
            actor="revenue-lab-builder",
            event_type="public_projection_ready",
            new_state="DESIGN_PREVIEW",
            action="Published the first no-login dashboard projection.",
            outcome="The page is explicit about preview data and awaits live worker evidence.",
            artifact_refs=["dashboard/index.html", "dashboard/data/latest.json"],
            source="local_build",
            public_summary="Public Mission Control preview is available.",
        ),
    ]
    packets = [
        WorkPacket(
            packet_id="packet-foundation-001",
            mission_id=mission.mission_id,
            kind="architecture",
            title="Interchangeable mission contract",
            state="COMPLETE",
            input_summary="Owner brief: Bitcoin first, other revenue missions later.",
            output_summary="Mission and worker boundaries do not hard-code KeyHunt or one provider.",
            actor="revenue-lab-builder",
            source="local_build",
            started_at=now,
            completed_at=now,
            duration_seconds=0.0,
            evidence_event_id="preview-foundation-001",
        ),
        WorkPacket(
            packet_id="packet-dashboard-001",
            mission_id=mission.mission_id,
            kind="evidence",
            title="Public evidence projection",
            state="COMPLETE",
            input_summary="Need visible work, machine proof, and honest economics.",
            output_summary="Dashboard schema separates estimated credit, confirmed payout, and money received.",
            actor="revenue-lab-builder",
            source="local_build",
            started_at=now,
            completed_at=now,
            duration_seconds=0.0,
            evidence_event_id="preview-dashboard-001",
        ),
    ]
    return PublicSnapshot(
        schema_version="1.0",
        mode="design-preview",
        status="DESIGN_PREVIEW",
        updated_at=now,
        mission=mission,
        worker=WorkerSnapshot(
            worker_id="btc-sha256d-001",
            worker_type="Bitcoin SHA-256d adapter",
            state="NOT_CONNECTED",
            lane="bitcoin",
            evidence_quality="not_connected",
            note="The adapter boundary is ready; live pool credentials and worker choice are intentionally not connected in the preview.",
        ),
        agents=[
            AgentSnapshot(
                agent_id="manager-core",
                role="Mission manager",
                provider="local runtime",
                model="contract-first",
                state="READY",
                current_action="Waiting for the first live worker adapter.",
                work_packets=2,
                last_update=now,
                capability_basis="tested_contract",
            ),
            AgentSnapshot(
                agent_id="evidence-steward",
                role="Evidence steward",
                provider="local runtime",
                model="sanitizer",
                state="READY",
                current_action="Projecting work and economics into public JSON.",
                work_packets=1,
                last_update=now,
                capability_basis="tested_contract",
            ),
        ],
        machine=MachineSnapshot(
            state="AVAILABLE",
            evidence_quality="awaiting_worker",
            sampled_at=now,
        ),
        finance=FinanceSnapshot(
            visibility=VisibilityMode.PUBLIC_EXACT,
            currency="USD",
            target_amount=20.0,
            estimated_credit=0.0,
            confirmed_payout=0.0,
            money_received=0.0,
            reserve_amount=0.0,
            target_label="Monthly subscription",
            cost_quality="unknown_shared_bill",
            note="Preview only: no live revenue or wallet is connected.",
        ),
        work_packets=packets,
        events=events,
        references=[
            {
                "reference_id": "ref-first-mission",
                "title": "Owner mission brief",
                "kind": "design_input",
                "source": "owner conversation",
                "observed_at": now,
                "review_by": review_by,
                "status": "active_design_input",
            },
            {
                "reference_id": "ref-live-principle-pending",
                "title": "Live Reference Principle",
                "kind": "architecture_reference",
                "source": "pending source review",
                "observed_at": now,
                "review_by": review_by,
                "status": "pending_source_location",
            },
        ],
        scenarios=[
            {
                "scenario_id": "public-projection-sanitization-001",
                "category": "public_data",
                "status": "PASS",
                "result": "Forbidden field names are rejected before publication.",
                "source": "local test suite",
            },
            {
                "scenario_id": "bitcoin-worker-live-001",
                "category": "worker_integration",
                "status": "NOT_RUN",
                "result": "Awaiting a selected SHA-256d worker and pool configuration.",
                "source": "planned experiment",
            },
            {
                "scenario_id": "payout-reconciliation-001",
                "category": "economics",
                "status": "NOT_RUN",
                "result": "Awaiting confirmed pool credit and a receiving address.",
                "source": "planned experiment",
            },
        ],
    )

