"""Provider adapter for ElevenLabs Scribe v2 batch transcription."""
from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlparse

from language_support import normalize_language

SCRIBE_LANGUAGE_CODES = {
    "ru-RU": "rus",
    "ky-KG": "kir",
    "kk-KZ": "kaz",
    "uz-UZ": "uzb",
}


def get_scribe_language_code(language: str) -> str:
    locale = normalize_language(language)
    if locale is None or locale not in SCRIBE_LANGUAGE_CODES:
        raise ValueError("Unsupported language; use ru, ky, kk, or uz")
    return SCRIBE_LANGUAGE_CODES[locale]


def validate_audio_source_url(url: str, allowed_hosts: list[str]) -> str:
    if not isinstance(url, str) or not url.strip():
        raise ValueError("audio_url is required")
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Audio source must be an HTTPS URL")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Audio source URL must not contain credentials or fragments")
    hostname = parsed.hostname.lower().rstrip(".")
    try:
        ip = ipaddress.ip_address(hostname)
        if not ip.is_global:
            raise ValueError("Private or non-global audio source addresses are not allowed")
    except ValueError as exc:
        if "not allowed" in str(exc):
            raise
        # Hostname is not an IP address; continue with the configured allowlist.
    normalized_hosts = [h.strip().lower().rstrip(".") for h in allowed_hosts if h.strip()]
    if not any(hostname == host or hostname.endswith("." + host) for host in normalized_hosts):
        raise ValueError("Audio source host is not in TRANSCRIPTION_ALLOWED_HOSTS")
    return url.strip()


async def transcribe_source_url(
    audio_url: str,
    language: str = "",
    diarize: bool = True,
    tag_audio_events: bool = True,
) -> dict:
    if os.environ.get("MCP_ALLOW_PAID_AI", "false").lower() != "true":
        raise PermissionError("Paid AI operations are disabled by default")
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not configured")
    allowed_hosts = os.environ.get("TRANSCRIPTION_ALLOWED_HOSTS", "").split(",")
    safe_url = validate_audio_source_url(audio_url, allowed_hosts)

    form = {
        "model_id": "scribe_v2",
        "diarize": str(bool(diarize)).lower(),
        "tag_audio_events": str(bool(tag_audio_events)).lower(),
        "timestamps_granularity": "word",
    }
    if language.strip():
        form["language_code"] = get_scribe_language_code(language)

    import httpx
    async with httpx.AsyncClient(verify=True, timeout=120.0, follow_redirects=False) as client:
        response = await client.post(
            "https://api.elevenlabs.io/v1/speech-to-text",
            headers={"xi-api-key": api_key},
            data=form,
            params={"enable_logging": "true"},
            json=None,
        )
        response.raise_for_status()
        result = response.json()

    if not isinstance(result, dict) or not isinstance(result.get("text"), str):
        raise RuntimeError("ElevenLabs returned an unexpected transcription response")
    return {
        "provider": "elevenlabs",
        "model": "scribe_v2",
        "language_code": result.get("language_code"),
        "language_probability": result.get("language_probability"),
        "text": result["text"],
        "words": result.get("words", []),
        "audio_events": result.get("audio_events", []),
    }
