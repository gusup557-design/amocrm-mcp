"""Safe lifecycle helpers for a persistent amoCRM account catalogue."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


_PUBLIC_FIELDS = (
    "account_id",
    "account_name",
    "base_domain",
    "expires_at",
    "created_at",
    "guarantee_until",
)


def resolve_connection_for_session(
    rows: Sequence[Mapping[str, Any]],
    selected_account_id: int | str | None,
) -> Mapping[str, Any]:
    """Resolve the account selected for this MCP session, never a global default."""
    if not rows:
        raise RuntimeError("amoCRM is not connected. Add an account through /connect first.")

    if selected_account_id is not None:
        selected = str(selected_account_id)
        for row in rows:
            if str(row.get("account_id", "")) == selected:
                return row
        raise LookupError(
            "The selected amoCRM account is no longer connected. Select another account."
        )

    if len(rows) == 1:
        return rows[0]

    raise RuntimeError(
        "Multiple amoCRM accounts are connected. Call select_amocrm_account(account_id) "
        "to choose the account for this MCP session before using CRM tools."
    )


def ensure_disconnect_confirmation(confirm_disconnect: bool) -> None:
    """Require explicit operator confirmation before deleting a local OAuth connection."""
    if confirm_disconnect is not True:
        raise PermissionError(
            "Disconnecting removes the MCP-stored OAuth credentials. "
            "Set confirm_disconnect=true to proceed."
        )


def public_connection_summaries(
    rows: Sequence[Mapping[str, Any]],
    selected_account_id: int | str | None = None,
) -> list[dict[str, Any]]:
    """Expose safe catalogue metadata only; never return token or secret fields."""
    selected = str(selected_account_id) if selected_account_id is not None else None
    summaries: list[dict[str, Any]] = []
    for row in rows:
        item = {field: row[field] for field in _PUBLIC_FIELDS if field in row}
        item["selected"] = (
            selected is not None and str(row.get("account_id", "")) == selected
        )
        summaries.append(item)
    return summaries
