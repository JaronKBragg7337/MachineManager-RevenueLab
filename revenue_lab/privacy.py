"""Public projection rules for telemetry and finance."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .models import FinanceSnapshot, PublicSnapshot, VisibilityMode, as_jsonable


SENSITIVE_KEY_PARTS = (
    "private_key",
    "privatekey",
    "seed",
    "mnemonic",
    "xprv",
    "token",
    "password",
    "secret",
    "api_key",
    "credential",
    "cookie",
    "authorization",
)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def _mask_address(address: str | None) -> str | None:
    if not address:
        return None
    if len(address) <= 12:
        return "*" * len(address)
    return f"{address[:6]}...{address[-6:]}"


def _round_money(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 2)


def project_finance(finance: FinanceSnapshot) -> dict[str, Any]:
    """Return only the financial fields permitted by the selected visibility mode."""

    mode = VisibilityMode(finance.visibility)
    base: dict[str, Any] = {
        "visibility": mode.value,
        "currency": finance.currency,
        "target_label": finance.target_label,
        "cost_quality": finance.cost_quality,
    }

    if mode is VisibilityMode.PRIVATE:
        base.update(
            {
                "target_amount": None,
                "estimated_credit": None,
                "confirmed_payout": None,
                "money_received": None,
                "reserve_amount": None,
                "wallet": None,
                "public_note": "Finance is private in this deployment.",
            }
        )
        return base

    if mode is VisibilityMode.MASKED:
        base.update(
            {
                "target_amount": None,
                "estimated_credit": None,
                "confirmed_payout": None,
                "money_received": None,
                "reserve_amount": None,
                "wallet": {
                    "label": finance.wallet_label,
                    "address": _mask_address(finance.wallet_public_address),
                    "balance": None,
                },
                "public_note": "Financial activity is present only as a masked signal.",
            }
        )
        return base

    if mode is VisibilityMode.PUBLIC_ROUNDED:
        formatter = _round_money
        address = _mask_address(finance.wallet_public_address)
    else:
        formatter = lambda value: value
        address = finance.wallet_public_address

    base.update(
        {
            "target_amount": formatter(finance.target_amount),
            "estimated_credit": formatter(finance.estimated_credit),
            "confirmed_payout": formatter(finance.confirmed_payout),
            "money_received": formatter(finance.money_received),
            "reserve_amount": formatter(finance.reserve_amount),
            "wallet": {
                "label": finance.wallet_label,
                "address": address,
                "balance": formatter(finance.wallet_balance),
                "last_payout_at": finance.last_payout_at,
            },
            "public_note": finance.note,
        }
    )
    return base


def _remove_sensitive_keys(value: Any) -> Any:
    """Defensively remove sensitive-looking keys from an already public record."""

    if isinstance(value, dict):
        return {
            key: _remove_sensitive_keys(item)
            for key, item in value.items()
            if not _is_sensitive_key(str(key))
        }
    if isinstance(value, list):
        return [_remove_sensitive_keys(item) for item in value]
    return value


def sanitize_snapshot(snapshot: PublicSnapshot) -> dict[str, Any]:
    """Create the compact, allowlist-shaped projection consumed by the website."""

    raw = as_jsonable(deepcopy(snapshot))
    raw["finance"] = project_finance(snapshot.finance)
    projected = _remove_sensitive_keys(raw)
    validate_public_payload(projected)
    return projected


def validate_public_payload(payload: Any) -> None:
    """Fail closed if a public projection contains a forbidden field name."""

    def visit(value: Any, path: str = "payload") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if _is_sensitive_key(str(key)):
                    raise ValueError(f"sensitive field in public payload: {path}.{key}")
                visit(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    visit(payload)

