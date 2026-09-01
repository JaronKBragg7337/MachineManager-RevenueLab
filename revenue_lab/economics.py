"""Transparent progress calculations for the subscription milestone."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EconomicAssessment:
    target_amount: float | None
    reserve_amount: float | None
    progress_pct: float | None
    status: str
    quality: str


def assess_reserve(
    target_amount: float | None,
    reserve_amount: float | None,
    *,
    quality: str = "unknown_shared_bill",
) -> EconomicAssessment:
    """Calculate progress without confusing estimates with received money."""

    if target_amount is None or reserve_amount is None:
        return EconomicAssessment(target_amount, reserve_amount, None, "PRIVATE", quality)
    if target_amount <= 0:
        raise ValueError("target_amount must be greater than zero")
    progress = min(100.0, max(0.0, (reserve_amount / target_amount) * 100.0))
    status = "GOAL_REACHED" if progress >= 100 else "BUILDING"
    return EconomicAssessment(target_amount, reserve_amount, progress, status, quality)


def reconcile_reserve(*, confirmed_payout: float, money_received: float, reserve_amount: float) -> None:
    """Reject accounting records that claim more reserve than observed receipts."""

    for name, value in {
        "confirmed_payout": confirmed_payout,
        "money_received": money_received,
        "reserve_amount": reserve_amount,
    }.items():
        if value < 0:
            raise ValueError(f"{name} cannot be negative")
    if money_received > confirmed_payout:
        raise ValueError("money_received cannot exceed confirmed_payout")
    if reserve_amount > money_received:
        raise ValueError("reserve_amount cannot exceed money_received")

