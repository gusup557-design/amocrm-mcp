"""Read-only planning of CRM follow-ups from completed voice conversations."""
from __future__ import annotations

from typing import Any

from language_support import DEFAULT_LANGUAGE, normalize_language


def _positive_id(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def build_post_call_action_plan(payload: Any) -> dict:
    """Build a deterministic, non-executing CRM action proposal."""
    if not isinstance(payload, dict):
        raise ValueError("Post-call payload must be an object")
    if payload.get("type") != "post_call_transcription":
        return {
            "status": "not_actionable",
            "conversation_id": None,
            "contact_id": None,
            "language": DEFAULT_LANGUAGE,
            "proposed_actions": [],
            "requires": "completed_transcription_event",
        }

    data = payload.get("data")
    if not isinstance(data, dict) or data.get("status") != "done":
        return {
            "status": "not_actionable",
            "conversation_id": data.get("conversation_id") if isinstance(data, dict) else None,
            "contact_id": None,
            "language": DEFAULT_LANGUAGE,
            "proposed_actions": [],
            "requires": "completed_transcription_event",
        }

    initiation = data.get("conversation_initiation_client_data")
    dynamic = initiation.get("dynamic_variables") if isinstance(initiation, dict) else {}
    if not isinstance(dynamic, dict):
        dynamic = {}

    contact_id = _positive_id(
        dynamic.get("crm_contact_id", dynamic.get("contact_id"))
    )
    language = (
        normalize_language(dynamic.get("preferred_language"))
        or normalize_language(dynamic.get("detected_language"))
        or DEFAULT_LANGUAGE
    )

    analysis = data.get("analysis")
    if not isinstance(analysis, dict):
        analysis = {}
    summary = analysis.get("transcript_summary")
    if not isinstance(summary, str):
        summary = ""
    summary = summary.strip()[:4000]

    conversation_id = data.get("conversation_id")
    if not isinstance(conversation_id, str):
        conversation_id = None

    if contact_id is None:
        return {
            "status": "needs_contact_match",
            "conversation_id": conversation_id,
            "contact_id": None,
            "language": language,
            "call_successful": analysis.get("call_successful"),
            "summary": summary,
            "proposed_actions": [],
            "requires": "contact_match",
        }

    if not summary:
        return {
            "status": "needs_review",
            "conversation_id": conversation_id,
            "contact_id": contact_id,
            "language": language,
            "call_successful": analysis.get("call_successful"),
            "summary": "",
            "proposed_actions": [],
            "requires": "human_summary_review",
        }

    note_text = (
        f"AI call summary ({language}; conversation {conversation_id or 'unknown'}):\n"
        f"{summary}"
    )
    return {
        "status": "ready_for_review",
        "conversation_id": conversation_id,
        "contact_id": contact_id,
        "language": language,
        "call_successful": analysis.get("call_successful"),
        "summary": summary,
        "proposed_actions": [
            {
                "type": "add_note",
                "entity_type": "contacts",
                "entity_id": contact_id,
                "text": note_text,
                "requires_confirmation": True,
            },
            {
                "type": "create_follow_up_task",
                "entity_type": "contacts",
                "entity_id": contact_id,
                "text": "Связаться с клиентом по итогам AI-звонка",
                "requires_confirmation": True,
            },
        ],
        "requires": "explicit_confirmation",
    }
