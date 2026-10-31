"""Single-active-account policy for the operator-driven amoCRM MCP workflow."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


_PUBLIC_FIELDS = ("account_id", "base_domain", "expires_at")


def select_single_active_connection(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Return the only connected account; never guess when state is ambiguous."""
    if not rows:
        raise RuntimeError("amoCRM is not connected. Open /connect first.")
    if len(rows) != 1:
        raise RuntimeError(
            "More than one amoCRM account is connected. Disconnect all but one "
            "account before using CRM tools."
        )
    return rows[0]


def ensure_no_other_active_account(
    rows: Sequence[Mapping[str, Any]], requested_account_id: int | str
) -> None:
    """Allow reconnecting the same account, but reject switching without disconnect."""
    requested = str(requested_account_id)
    for row in rows:
        existing = str(row.get("account_id", ""))
        if existing and existing != requested:
            raise PermissionError(
                "A different amoCRM account is already connected. Disconnect it "
                "through the MCP before connecting another client account."
            )


def ensure_disconnect_confirmation(confirm_disconnect: bool) -> None:
    """Require an explicit boolean confirmation for local credential deletion."""
    if confirm_disconnect is not True:
        raise PermissionError(
            "Disconnecting removes the MCP-stored OAuth credentials. "
            "Set confirm_disconnect=true to proceed."
        )


def public_connection_summaries(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Expose only safe account metadata, never tokens, secrets, or encrypted blobs."""
    return [
        {field: row[field] for field in _PUBLIC_FIELDS if field in row}
        for row in rows
    ]
