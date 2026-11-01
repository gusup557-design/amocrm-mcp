"""Stable identities for idempotent communication webhook ingestion."""
from __future__ import annotations

import hashlib
from typing import Any


def build_webhook_event_identity(
    provider: str,
    payload: Any,
    raw_body: bytes,
) -> tuple[str, str, str, str | None]:
    """Return provider, event type, idempotency key and conversation ID."""
    if provider not in {"amocrm_chat", "elevenlabs"}:
        raise ValueError("Unsupported webhook provider")
    if not isinstance(payload, dict):
        raise ValueError("Webhook payload must be a JSON object")
    if not isinstance(raw_body, bytes):
        raise ValueError("raw_body must be bytes")

    if provider == "amocrm_chat":
        event_type = payload.get("event_type")
        event_payload = payload.get("payload")
        if not isinstance(event_type, str) or not event_type:
            raise ValueError("Chat webhook event_type is required")
        if not isinstance(event_payload, dict):
            raise ValueError("Chat webhook payload must be an object")
        conversation_id = event_payload.get("conversation_id")
        message_id = event_payload.get("msgid")
        if not isinstance(message_id, str) or not message_id.strip():
            message_id = hashlib.sha256(raw_body).hexdigest()
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            conversation_id = None
        return provider, event_type, message_id, conversation_id

    event_type = payload.get("type")
    data = payload.get("data")
    if not isinstance(event_type, str) or not event_type:
        raise ValueError("ElevenLabs webhook type is required")
    if not isinstance(data, dict):
        raise ValueError("ElevenLabs webhook data must be an object")
    conversation_id = data.get("conversation_id")
    if not isinstance(conversation_id, str) or not conversation_id.strip():
        conversation_id = None
    timestamp = payload.get("event_timestamp")
    if conversation_id and timestamp is not None:
        event_id = f"{event_type}:{conversation_id}:{timestamp}"
    else:
        event_id = hashlib.sha256(raw_body).hexdigest()
    return provider, event_type, event_id, conversation_id
