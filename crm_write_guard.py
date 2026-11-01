"""Explicit per-call confirmation for operations that mutate amoCRM."""


def require_explicit_confirmation(confirmed: bool, parameter_name: str) -> None:
    """Fail closed unless the caller passes the literal boolean True."""
    if confirmed is not True:
        raise PermissionError(
            f"Set {parameter_name}=true only after reviewing and approving this CRM operation"
        )
