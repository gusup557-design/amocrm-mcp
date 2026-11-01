"""Fail-closed guard for provider credentials that are still process-global."""


def ensure_global_provider_scope(connection_count: int, provider_name: str) -> None:
    """Permit a global provider secret only when at most one CRM account is connected."""
    if isinstance(connection_count, bool) or not isinstance(connection_count, int) or connection_count < 0:
        raise ValueError("connection_count must be a non-negative integer")
    if not isinstance(provider_name, str) or not provider_name.strip():
        raise ValueError("provider_name is required")
    if connection_count == 0:
        raise RuntimeError(
            "No amoCRM account is connected. Connect the account before using provider integrations."
        )
    if connection_count > 1:
        raise PermissionError(
            f"{provider_name} is disabled while multiple amoCRM accounts are connected because "
            "its credentials are not account-specific yet. CRM REST tools remain available; "
            "use account-scoped provider credentials before enabling this integration."
        )
