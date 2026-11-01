"""Guarded outbound-call adapter for ElevenLabs Conversational AI over SIP."""
from __future__ import annotations

import os
import re

from language_support import normalize_language


_E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")


def validate_outbound_number(number: str, allowed_numbers: list[str]) -> str:
    if not isinstance(number, str) or not _E164.fullmatch(number.strip()):
        raise ValueError("Destination must be an E.164 phone number")
    if number.strip() not in {item.strip() for item in allowed_numbers if item.strip()}:
        raise ValueError("Destination number is not in VOICE_CALL_ALLOWED_NUMBERS")
    return number.strip()


def build_outbound_call_payload(
    agent_id: str,
    phone_number_id: str,
    to_number: str,
    crm_contact_id: int | str | None = None,
    preferred_language: str = "",
) -> dict:
    """Build SIP call request with optional CRM correlation metadata."""
    payload = {
        "agent_id": agent_id,
        "agent_phone_number_id": phone_number_id,
        "to_number": to_number,
    }
    dynamic_variables = {}
    if crm_contact_id not in (None, "", 0):
        if isinstance(crm_contact_id, bool):
            raise ValueError("crm_contact_id must be a positive integer")
        try:
            contact_id = int(crm_contact_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("crm_contact_id must be a positive integer") from exc
        if contact_id <= 0:
            raise ValueError("crm_contact_id must be a positive integer")
        dynamic_variables["crm_contact_id"] = str(contact_id)
    if preferred_language.strip():
        locale = normalize_language(preferred_language)
        if locale is None:
            raise ValueError("preferred_language must be ru, ky, kk, or uz")
        dynamic_variables["preferred_language"] = locale
    if dynamic_variables:
        payload["conversation_initiation_client_data"] = {
            "dynamic_variables": dynamic_variables
        }
    return payload


async def start_outbound_call(
    to_number: str,
    confirm_call: bool = False,
    crm_contact_id: int | str | None = None,
    preferred_language: str = "",
) -> dict:
    if not confirm_call:
        raise PermissionError("Each outbound call requires explicit confirm_call=true")
    if os.environ.get("MCP_ALLOW_PAID_AI", "false").lower() != "true":
        raise PermissionError("Paid AI operations are disabled by default")
    if os.environ.get("MCP_ALLOW_OUTBOUND_CALLS", "false").lower() != "true":
        raise PermissionError("Outbound calls are disabled by default")

    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    agent_id = os.environ.get("ELEVENLABS_AGENT_ID", "").strip()
    phone_number_id = os.environ.get("ELEVENLABS_PHONE_NUMBER_ID", "").strip()
    if not api_key or not agent_id or not phone_number_id:
        raise RuntimeError(
            "ELEVENLABS_API_KEY, ELEVENLABS_AGENT_ID and ELEVENLABS_PHONE_NUMBER_ID are required"
        )

    allowed_numbers = os.environ.get("VOICE_CALL_ALLOWED_NUMBERS", "").split(",")
    destination = validate_outbound_number(to_number, allowed_numbers)

    import httpx
    async with httpx.AsyncClient(verify=True, timeout=30.0, follow_redirects=False) as client:
        response = await client.post(
            "https://api.elevenlabs.io/v1/convai/sip-trunk/outbound-call",
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json=build_outbound_call_payload(
                agent_id=agent_id,
                phone_number_id=phone_number_id,
                to_number=destination,
                crm_contact_id=crm_contact_id,
                preferred_language=preferred_language,
            ),
        )
        response.raise_for_status()
        result = response.json()

    if not isinstance(result, dict) or result.get("success") is not True:
        raise RuntimeError("ElevenLabs did not confirm that the outbound call was started")
    return {
        "provider": "elevenlabs",
        "success": True,
        "conversation_id": result.get("conversation_id"),
        "sip_call_id": result.get("sip_call_id"),
        "message": result.get("message"),
    }
