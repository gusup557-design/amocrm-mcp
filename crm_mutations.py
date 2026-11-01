"""Input validation for guarded amoCRM entity and task updates."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


_ENTITY_FIELDS = {
    "contacts": {
        "name", "first_name", "last_name", "responsible_user_id",
        "custom_fields_values", "tags_to_add", "tags_to_delete", "_embedded",
    },
    "companies": {
        "name", "responsible_user_id", "custom_fields_values",
        "tags_to_add", "tags_to_delete", "_embedded",
    },
}
_TASK_FIELDS = {
    "responsible_user_id",
    "entity_id",
    "entity_type",
    "is_completed",
    "task_type_id",
    "text",
    "duration",
    "complete_till",
    "result",
}
_ENTITY_TYPES = {"leads", "contacts", "companies", "customers"}
_TAG_KEYS = {"id", "name"}


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate_tags(value: Any, key: str) -> None:
    if not isinstance(value, list):
        raise ValueError(key + " must be an array")
    for tag in value:
        if not isinstance(tag, Mapping):
            raise ValueError("each tag must be an object")
        if set(tag) - _TAG_KEYS:
            raise ValueError("tag supports only id or name")
        has_id = "id" in tag
        has_name = "name" in tag
        if has_id == has_name:
            raise ValueError("each tag must contain exactly one of id or name")
        if has_id and not _positive_int(tag["id"]):
            raise ValueError("tag id must be a positive integer")
        if has_name and (not isinstance(tag["name"], str) or not tag["name"].strip()):
            raise ValueError("tag name must be a non-empty string")


def _validate_custom_fields(value: Any) -> None:
    if not isinstance(value, list):
        raise ValueError("custom_fields_values must be an array")
    for field in value:
        if not isinstance(field, Mapping):
            raise ValueError("each custom field value must be an object")
        if set(field) - {"field_id", "field_code", "values"}:
            raise ValueError("custom field value contains unsupported properties")
        if ("field_id" in field) == ("field_code" in field):
            raise ValueError("custom field value requires exactly one of field_id or field_code")
        if "field_id" in field and not _positive_int(field["field_id"]):
            raise ValueError("custom field id must be a positive integer")
        if "field_code" in field and (
            not isinstance(field["field_code"], str) or not field["field_code"].strip()
        ):
            raise ValueError("custom field code must be a non-empty string")
        values = field.get("values")
        if not isinstance(values, list) or not values:
            raise ValueError("custom field values must be a non-empty array")
        for item in values:
            if not isinstance(item, Mapping) or "value" not in item or set(item) - {
                "value", "enum_id", "enum_code"
            }:
                raise ValueError("custom field value entry is invalid")


def validate_entity_update_payload(entity_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate supported Contact or Company update fields; reject API/system metadata."""
    if not isinstance(entity_type, str) or entity_type not in _ENTITY_FIELDS:
        raise ValueError("entity_type must be contacts or companies")
    if not isinstance(payload, dict) or not payload:
        raise ValueError("entity update payload must be a non-empty object")
    unsupported = set(payload) - _ENTITY_FIELDS[entity_type]
    if unsupported:
        raise ValueError("unsupported or read-only entity properties: " + ", ".join(sorted(unsupported)))

    if "name" in payload and (
        not isinstance(payload["name"], str) or not payload["name"].strip()
    ):
        raise ValueError("name must be a non-empty string")
    for key in ("first_name", "last_name"):
        if key in payload and (not isinstance(payload[key], str) or not payload[key].strip()):
            raise ValueError(key + " must be a non-empty string")
    if "responsible_user_id" in payload and not _positive_int(payload["responsible_user_id"]):
        raise ValueError("responsible_user_id must be a positive integer")
    if "custom_fields_values" in payload:
        _validate_custom_fields(payload["custom_fields_values"])
    for key in ("tags_to_add", "tags_to_delete"):
        if key in payload:
            _validate_tags(payload[key], key)
    if "_embedded" in payload:
        embedded = payload["_embedded"]
        if not isinstance(embedded, Mapping) or set(embedded) - {"tags"}:
            raise ValueError("_embedded supports only tags")
        if "tags" in embedded:
            _validate_tags(embedded["tags"], "_embedded.tags")
    return dict(payload)


def validate_task_update_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate documented amoCRM task fields and completion result requirements."""
    if not isinstance(payload, dict) or not payload:
        raise ValueError("task update payload must be a non-empty object")
    unsupported = set(payload) - _TASK_FIELDS
    if unsupported:
        raise ValueError("unsupported or read-only task properties: " + ", ".join(sorted(unsupported)))
    if "text" in payload and (
        not isinstance(payload["text"], str) or not payload["text"].strip()
    ):
        raise ValueError("text must be a non-empty string")
    if "responsible_user_id" in payload and not _positive_int(payload["responsible_user_id"]):
        raise ValueError("responsible_user_id must be a positive integer")
    if "entity_id" in payload and not _positive_int(payload["entity_id"]):
        raise ValueError("entity_id must be a positive integer")
    if "entity_type" in payload and payload["entity_type"] not in _ENTITY_TYPES:
        raise ValueError("entity_type must be leads, contacts, companies or customers")
    if "is_completed" in payload and not isinstance(payload["is_completed"], bool):
        raise ValueError("is_completed must be boolean")
    if "task_type_id" in payload and not _positive_int(payload["task_type_id"]):
        raise ValueError("task_type_id must be a positive integer")
    if "duration" in payload and not _non_negative_int(payload["duration"]):
        raise ValueError("duration must be a non-negative integer")
    if "complete_till" in payload and not _positive_int(payload["complete_till"]):
        raise ValueError("complete_till must be a positive Unix timestamp")
    if "result" in payload:
        result = payload["result"]
        if not isinstance(result, Mapping) or set(result) - {"text"}:
            raise ValueError("result must be an object with a text property")
        if not isinstance(result.get("text"), str) or not result["text"].strip():
            raise ValueError("result.text must be a non-empty string")
    if payload.get("is_completed") is True and "result" not in payload:
        raise ValueError("completing a task requires result.text")
    return dict(payload)
