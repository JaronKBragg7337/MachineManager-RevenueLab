"""Financial evidence helpers; receiving and returning are separate events."""

from __future__ import annotations

from .models import ReceiptClassification, ReceiptRecord


def classify_receipt(*, expected: bool, confirmations: int) -> ReceiptClassification:
    """Classify an observed receipt without initiating any transaction."""

    if confirmations < 0:
        raise ValueError("confirmations cannot be negative")
    return ReceiptClassification.EXPECTED if expected else ReceiptClassification.UNRECOGNIZED


def can_propose_return(receipt: ReceiptRecord) -> bool:
    """Require a confirmed, unrecognized receipt before a return can be proposed."""

    return (
        receipt.classification is ReceiptClassification.UNRECOGNIZED
        and receipt.confirmations >= 1
        and receipt.status == "confirmed"
        and bool(receipt.txid)
    )


def mark_return_proposed(receipt: ReceiptRecord) -> ReceiptRecord:
    """Record a proposal; this never sends a transaction or chooses a destination."""

    if not can_propose_return(receipt):
        raise ValueError("receipt is not confirmed and eligible for a return proposal")
    return ReceiptRecord(
        receipt_id=receipt.receipt_id,
        asset=receipt.asset,
        amount=receipt.amount,
        txid=receipt.txid,
        confirmations=receipt.confirmations,
        classification=ReceiptClassification.RETURN_PROPOSED,
        status="proposal_recorded",
        observed_at=receipt.observed_at,
        source=receipt.source,
        note="A return destination must be verified separately; no automatic refund was sent.",
    )

