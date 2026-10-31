"""Webhook signature verification for amoCRM Chat API and ElevenLabs.

These helpers only authenticate raw webhook requests. Persistence, event routing,
and business automation are intentionally implemented by separate layers.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import time
from typing import Optional


_HEX_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_TIMESTAMP = re.compile(r"^[0-9]{1,12}$")


def verify_amocrm_chat_signature(
    raw_body: bytes,
    signature: str,
    channel_secret: str,
) -> bool:
    """Verify amoCRM Chat API HMAC-SHA1 over the trimmed raw request body."""
    if not isinstance(raw_body, bytes):
        return False
    if not isinstance(channel_secret, str) or not channel_secret.strip():
        return False
    if not isinstance(signature, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", signature.strip()):
        return False
    expected = hmac.new(
        channel_secret.encode("utf-8"),
        raw_body.strip(),
        hashlib.sha1,
    ).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


def verify_elevenlabs_signature(
    raw_body: bytes,
    signature_header: str,
    webhook_secret: str,
    *,
    now: Optional[int] = None,
    tolerance_seconds: int = 1800,
) -> bool:
    """Verify ElevenLabs t=...,v0=... HMAC-SHA256 with replay-window checks."""
    if not isinstance(raw_body, bytes):
        return False
    if not isinstance(webhook_secret, str) or not webhook_secret:
        return False
    if not isinstance(signature_header, str) or not signature_header.strip():
        return False
    if not isinstance(tolerance_seconds, int) or tolerance_seconds < 0:
        return False

    parts: dict[str, str] = {}
    for item in signature_header.split(","):
        key, separator, value = item.strip().partition("=")
        if not separator or key not in {"t", "v0"} or key in parts:
            return False
        parts[key] = value

    timestamp = parts.get("t", "")
    signature = parts.get("v0", "")
    if not _TIMESTAMP.fullmatch(timestamp) or not _HEX_SHA256.fullmatch(signature):
        return False

    timestamp_value = int(timestamp)
    current_time = int(time.time()) if now is None else int(now)
    if abs(current_time - timestamp_value) > tolerance_seconds:
        return False

    signed_payload = timestamp.encode("ascii") + b"." + raw_body
    expected = hmac.new(
        webhook_secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature.lower())
