"""Minimal, server-side amoCRM Chat API client and request signing."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Any, Mapping, Optional
from urllib.parse import quote

import httpx

_ALLOWED_METHODS = {"GET", "POST", "DELETE"}


def build_chat_headers(
    method: str,
    path: str,
    body: bytes,
    secret: str,
    date_header: Optional[str] = None,
    content_type: str = "application/json",
) -> dict[str, str]:
    """Build the documented amoCRM Chat API Date/MD5/HMAC-SHA1 headers."""
    normalized_method = method.upper().strip()
    if normalized_method not in _ALLOWED_METHODS:
        raise ValueError("Chat API method must be GET, POST, or DELETE")
    if not isinstance(path, str) or not path.startswith("/") or "?" in path or "#" in path:
        raise ValueError("Signed path must be an absolute URL path without query or fragment")
    if not isinstance(body, bytes):
        raise TypeError("body must be bytes")
    if not isinstance(secret, str) or not secret.strip():
        raise ValueError("Chat API channel secret is required")

    date_value = date_header or format_datetime(datetime.now(timezone.utc))
    checksum = hashlib.md5(body).hexdigest()
    canonical = "\n".join(
        (normalized_method, checksum, content_type, date_value, path)
    )
    signature = hmac.new(
        secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha1
    ).hexdigest().lower()
    return {
        "Date": date_value,
        "Content-Type": content_type,
        "Content-MD5": checksum.lower(),
        "X-Signature": signature,
    }


class AmoChatApiClient:
    """Async Chat API client. Channel secrets are never logged or returned."""

    def __init__(
        self,
        scope_id: str,
        secret: str,
        base_url: str = "https://amojo.amocrm.ru",
        timeout: float = 20.0,
    ) -> None:
        if not scope_id or not scope_id.strip():
            raise ValueError("AMOCHAT_SCOPE_ID is required")
        if not secret or not secret.strip():
            raise ValueError("AMOCHAT_CHANNEL_SECRET is required")
        if not base_url.startswith("https://"):
            raise ValueError("Chat API base URL must use HTTPS")
        self.scope_id = quote(scope_id.strip(), safe="")
        self.secret = secret
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def request(
        self,
        method: str,
        path_suffix: str,
        body: Optional[Mapping[str, Any]] = None,
        params: Optional[dict[str, int]] = None,
    ) -> dict[str, Any]:
        method = method.upper()
        if not path_suffix.startswith("/") or "?" in path_suffix or "#" in path_suffix:
            raise ValueError("Chat API path suffix must not contain query or fragment")
        path = f"/v2/origin/custom/{self.scope_id}{path_suffix}"
        body_bytes = (
            json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if body is not None
            else b""
        )
        headers = build_chat_headers(method, path, body_bytes, self.secret)
        async with httpx.AsyncClient(
            verify=True, timeout=self.timeout, follow_redirects=False
        ) as client:
            response = await client.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                content=body_bytes if body is not None else None,
                params=params,
            )
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()

    async def get_history(self, conversation_id: str, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        if not conversation_id or not conversation_id.strip():
            raise ValueError("conversation_id is required")
        if offset < 0 or not 1 <= limit <= 50:
            raise ValueError("offset must be >= 0 and limit must be from 1 to 50")
        conversation = quote(conversation_id.strip(), safe="")
        return await self.request(
            "GET",
            f"/chats/{conversation}/history",
            params={"offset": offset, "limit": limit},
        )

    async def send_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict) or payload.get("event_type") not in {"new_message", "edit_message"}:
            raise ValueError("payload must be a Chat API new_message or edit_message event")
        if not isinstance(payload.get("payload"), dict):
            raise ValueError("payload.event payload must be an object")
        return await self.request("POST", "", body=payload)
