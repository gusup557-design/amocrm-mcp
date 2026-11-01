"""Validation helpers for guarded amoCRM custom-field operations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


SUPPORTED_CUSTOM_FIELD_ENTITIES = frozenset({"leads", "contacts", "companies"})
_ENUM_FIELD_TYPES = frozenset({"select", "multiselect", "radiobutton"})
_CREATE_PROPERTIES = frozenset({
    "name",
    "type",
    "code",
    "sort",
    "group_id",
    "is_api_only",
    "required_statuses",
    "enums",
    "remind",
    "nested",
    "hidden_statuses",
    "chained_lists",
    "tracking_callback",
    "search_in",
    "currency",
})
_UPDATE_PROPERTIES = _CREATE_PROPERTIES - {"type"}


def normalize_custom_field_entity(entity_type: str) -> str:
    """Allow only standard CRM entity paths; never permit arbitrary API paths."""
    if not isinstance(entity_type, str) or entity_type not in SUPPORTED_CUSTOM_FIELD_ENTITIES:
        raise ValueError("entity_type must be leads, contacts, or companies")
    return entity_type


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _validate_enums(enums: Any, operation: str) -> None:
    if not isinstance(enums, list) or not enums:
        raise ValueError("enums must be a non-empty array for select, multiselect and radiobutton fields")
    seen_values: set[str] = set()
    for item in enums:
        if not isinstance(item, Mapping):
            raise ValueError("each enum must be an object")
        value = item.get("value")
        sort = item.get("sort")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("each enum requires a non-empty string value")
        if value in seen_values:
            raise ValueError("enum values must be unique")
        seen_values.add(value)
        if not isinstance(sort, int) or isinstance(sort, bool) or sort < 0:
            raise ValueError("each enum requires a non-negative integer sort")
        allowed = {"value", "sort", "code"}
        if operation == "update":
            allowed.add("id")
            if "id" in item and not _positive_int(item["id"]):
                raise ValueError("enum id must be a positive integer")
        if set(item) - allowed:
            raise ValueError("enum contains unsupported properties")
        if "code" in item and item["code"] is not None and not isinstance(item["code"], str):
            raise ValueError("enum code must be a string or null")


def validate_custom_field_payload(payload: dict[str, Any], operation: str) -> dict[str, Any]:
    """Validate writable field metadata against documented amoCRM request properties."""
    if operation not in {"create", "update"}:
        raise ValueError("operation must be create or update")
    if not isinstance(payload, dict) or not payload:
        raise ValueError("field payload must be a non-empty JSON object")

    allowed = _CREATE_PROPERTIES if operation == "create" else _UPDATE_PROPERTIES
    unsupported = set(payload) - allowed
    if unsupported:
        raise ValueError("unsupported or read-only field properties: " + ", ".join(sorted(unsupported)))

    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("a non-empty name is required for custom-field creation and update")

    if operation == "create":
        field_type = payload.get("type")
        if not isinstance(field_type, str) or not field_type.strip():
            raise ValueError("type is required for custom-field creation")
    else:
        field_type = None

    if "sort" in payload:
        sort = payload["sort"]
        if not isinstance(sort, int) or isinstance(sort, bool) or sort < 0:
            raise ValueError("sort must be a non-negative integer")
    if "group_id" in payload and payload["group_id"] is not None and not isinstance(payload["group_id"], str):
        raise ValueError("group_id must be a string or null")
    if "is_api_only" in payload and not isinstance(payload["is_api_only"], bool):
        raise ValueError("is_api_only must be boolean")

    if "required_statuses" in payload:
        items = payload["required_statuses"]
        if not isinstance(items, list):
            raise ValueError("required_statuses must be an array")
        for item in items:
            if not isinstance(item, Mapping):
                raise ValueError("required_statuses entries must be objects")
            if not _positive_int(item.get("pipeline_id")) or not _positive_int(item.get("status_id")):
                raise ValueError("each required_statuses entry needs positive pipeline_id and status_id")
            if set(item) - {"pipeline_id", "status_id"}:
                raise ValueError("required_statuses entry has unsupported properties")

    if "enums" in payload:
        _validate_enums(payload["enums"], operation)
    if operation == "create" and field_type in _ENUM_FIELD_TYPES:
        _validate_enums(payload.get("enums"), operation)

    if "remind" in payload and payload["remind"] not in {"never", "day", "week", "month", None}:
        raise ValueError("remind must be never, day, week, month or null")
    for key in ("nested", "hidden_statuses", "chained_lists"):
        if key in payload and not isinstance(payload[key], list):
            raise ValueError(key + " must be an array")
    if "tracking_callback" in payload and payload["tracking_callback"] is not None and not isinstance(payload["tracking_callback"], str):
        raise ValueError("tracking_callback must be a string or null")
    if "search_in" in payload and payload["search_in"] is not None and not isinstance(payload["search_in"], str):
        raise ValueError("search_in must be a string or null")
    if "currency" in payload and payload["currency"] is not None:
        currency = payload["currency"]
        if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha():
            raise ValueError("currency must be a three-letter currency code")

    return dict(payload)


def preserve_enum_ids_for_update(
    current_field: Mapping[str, Any],
    payload: dict[str, Any],
    confirm_enum_changes: bool,
) -> dict[str, Any]:
    """Preserve IDs for unchanged options and require confirmation before replacing enum values."""
    if "enums" not in payload:
        return dict(payload)
    if confirm_enum_changes is not True:
        raise PermissionError(
            "Changing enum options can invalidate existing option IDs. "
            "Set confirm_enum_changes=true after reviewing the complete replacement list."
        )
    existing = current_field.get("enums", [])
    existing_ids = {
        item.get("value"): item.get("id")
        for item in existing
        if isinstance(item, Mapping)
        and isinstance(item.get("value"), str)
        and _positive_int(item.get("id"))
    } if isinstance(existing, list) else {}
    updated = dict(payload)
    updated_enums = []
    for item in payload["enums"]:
        candidate = dict(item)
        if "id" not in candidate and candidate.get("value") in existing_ids:
            candidate["id"] = existing_ids[candidate["value"]]
        updated_enums.append(candidate)
    updated["enums"] = updated_enums
    return updated


def ensure_custom_field_is_deletable(field: Mapping[str, Any], expected_field_id: int) -> None:
    """Fail closed unless the exact field exists and amoCRM marks it deletable."""
    if not _positive_int(expected_field_id):
        raise ValueError("field_id must be a positive integer")
    if not isinstance(field, Mapping) or field.get("id") != expected_field_id:
        raise PermissionError("amoCRM returned a different custom field; refusing to delete")
    if field.get("is_deletable") is not True or field.get("is_predefined") is True:
        raise PermissionError(
            "amoCRM does not mark this custom field as deletable. "
            "Deleting a field permanently removes its values."
        )


_GROUP_ID_PATTERN = __import__("re").compile(r"^[A-Za-z0-9_-]{1,128}$")


def normalize_custom_field_group_id(group_id: str) -> str:
    """Validate an amoCRM field-group ID as a single safe path segment."""
    if not isinstance(group_id, str) or not _GROUP_ID_PATTERN.fullmatch(group_id):
        raise ValueError("group_id must contain only letters, digits, underscore or hyphen")
    return group_id


def validate_custom_field_group_payload(payload: dict[str, Any], operation: str) -> dict[str, Any]:
    """Validate the documented create/update properties for field groups."""
    if operation not in {"create", "update"}:
        raise ValueError("operation must be create or update")
    if not isinstance(payload, dict) or not payload:
        raise ValueError("group payload must be a non-empty JSON object")
    allowed = {"name", "sort"} if operation == "create" else {"name", "sort"}
    unsupported = set(payload) - allowed
    if unsupported:
        raise ValueError("unsupported group properties: " + ", ".join(sorted(unsupported)))
    if operation == "create" and "name" not in payload:
        raise ValueError("name is required for group creation")
    if "name" in payload and (not isinstance(payload["name"], str) or not payload["name"].strip()):
        raise ValueError("name must be a non-empty string")
    if operation == "create" and "sort" not in payload:
        raise ValueError("sort is required for group creation")
    if "sort" in payload and (
        not isinstance(payload["sort"], int)
        or isinstance(payload["sort"], bool)
        or payload["sort"] < 0
    ):
        raise ValueError("sort must be a non-negative integer")
    return dict(payload)


def ensure_custom_field_group_is_deletable(group: Mapping[str, Any], expected_group_id: str) -> None:
    """Fail closed for predefined/linked groups or mismatched response IDs."""
    if normalize_custom_field_group_id(expected_group_id) != expected_group_id:
        raise ValueError("invalid group_id")
    if not isinstance(group, Mapping) or group.get("id") != expected_group_id:
        raise PermissionError("amoCRM returned a different custom field group; refusing to delete")
    if group.get("is_predefined") is not False or group.get("type") != "custom_field_group":
        raise PermissionError(
            "Only non-predefined custom_field_group groups can be deleted."
        )
