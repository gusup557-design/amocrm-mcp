"""Validation and preflight checks for amoCRM sales-pipeline statuses."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


STATUS_COLORS = frozenset({
    "#fffeb2", "#fffd7f", "#fff000", "#ffeab2", "#ffdc7f", "#ffce5a",
    "#ffdbdb", "#ffc8c8", "#ff8f92", "#d6eaff", "#c1e0ff", "#98cbff",
    "#ebffb1", "#deff81", "#87f2c0", "#f9deff", "#f3beff", "#ccc8f9",
    "#eb93ff", "#f2f3f4", "#e6e8ea",
})
_DESCRIPTION_LEVELS = frozenset({"newbie", "candidate", "master"})


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def validate_pipeline_status_payload(payload: dict[str, Any], operation: str) -> dict[str, Any]:
    """Validate the documented create/update model without allowing system properties."""
    if operation not in {"create", "update"}:
        raise ValueError("operation must be create or update")
    if not isinstance(payload, dict) or not payload:
        raise ValueError("status payload must be a non-empty JSON object")
    allowed = {"name", "sort", "color", "descriptions"}
    unsupported = set(payload) - allowed
    if unsupported:
        raise ValueError("unsupported or read-only status properties: " + ", ".join(sorted(unsupported)))
    if operation == "create" and not {"name", "sort"}.issubset(payload):
        raise ValueError("status creation requires name and sort")
    if "name" in payload and (not isinstance(payload["name"], str) or not payload["name"].strip()):
        raise ValueError("name must be a non-empty string")
    if "sort" in payload and (
        not isinstance(payload["sort"], int)
        or isinstance(payload["sort"], bool)
        or payload["sort"] < 0
    ):
        raise ValueError("sort must be a non-negative integer")
    if "color" in payload and payload["color"] not in STATUS_COLORS:
        raise ValueError("color must be one of amoCRM's documented status colors")

    if "descriptions" in payload:
        descriptions = payload["descriptions"]
        if not isinstance(descriptions, list) or len(descriptions) > 3:
            raise ValueError("descriptions must be an array with at most three entries")
        seen_levels: set[str] = set()
        for item in descriptions:
            if not isinstance(item, Mapping):
                raise ValueError("each status description must be an object")
            level = item.get("level")
            if level not in _DESCRIPTION_LEVELS:
                raise ValueError("description level must be newbie, candidate or master")
            if level in seen_levels:
                raise ValueError("each description level can appear only once")
            seen_levels.add(level)
            allowed_description_keys = {"level", "description"}
            if operation == "update":
                allowed_description_keys.add("id")
            if set(item) - allowed_description_keys:
                raise ValueError("description contains unsupported properties")
            if "id" in item and not _positive_int(item["id"]):
                raise ValueError("description id must be a positive integer")
            if "description" in item:
                value = item["description"]
                if not isinstance(value, str) or not value.strip() or len(value) > 1000:
                    raise ValueError("description must be a non-empty string up to 1000 characters")
            elif operation == "create" or "id" not in item:
                raise ValueError("new descriptions require a description value")
    if operation == "update" and not set(payload).intersection({"name", "sort", "color", "descriptions"}):
        raise ValueError("at least one editable status property is required")
    return dict(payload)


def ensure_pipeline_status_is_editable(
    status: Mapping[str, Any],
    expected_pipeline_id: int,
    expected_status_id: int,
) -> None:
    """Prevent mutations against another pipeline or a non-editable/system status."""
    if (
        not _positive_int(expected_pipeline_id)
        or not _positive_int(expected_status_id)
    ):
        raise ValueError("pipeline_id and status_id must be positive integers")
    if not isinstance(status, Mapping):
        raise PermissionError("amoCRM did not return a status object")
    if status.get("id") != expected_status_id or status.get("pipeline_id") != expected_pipeline_id:
        raise PermissionError("amoCRM returned a different pipeline status; refusing mutation")
    if status.get("is_editable") is not True:
        raise PermissionError(
            "This pipeline status is not editable. System statuses cannot be modified or deleted."
        )
