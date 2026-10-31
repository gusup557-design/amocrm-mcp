"""Provider-aware, non-persistent client provisioning plans and SIP validation.

This module deliberately stores no customer profiles and performs no provider writes.
It generates a repeatable setup checklist for the one account currently connected
by the operator.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Any


_PROVIDER_CATALOG: dict[str, dict[str, Any]] = {
    "generic_sip": {
        "name": "Generic SIP trunk",
        "setup_mode": "manual",
        "api_adapter_status": "manual_only",
        "api_available": False,
        "api_operations": [],
        "manual_steps": [
            "Obtain SIP server host, port, transport, username and password from the carrier.",
            "Configure SIP registration or IP authentication at the PBX/carrier.",
            "Configure inbound and outbound routes, caller ID and allowed IP addresses.",
            "Run a controlled test call after the customer approves it.",
        ],
        "notes": ["The MCP validates non-secret endpoint parameters only; it does not provision a carrier account or SIP credentials."],
    },
    "zadarma": {
        "name": "Zadarma",
        "setup_mode": "api_and_manual",
        "api_adapter_status": "guide_only",
        "api_available": True,
        "api_operations": [
            "Zadarma publishes an API for account, virtual PBX and telephony operations.",
            "Provider-side operations are not executed by this setup guide; an adapter must be separately configured and tested.",
        ],
        "manual_steps": [
            "The account owner creates or supplies an API key and secret in the Zadarma cabinet.",
            "The owner selects a virtual PBX/number and checks service availability for the destination country.",
            "The operator configures SIP extensions, routing, caller ID and webhook URLs in the provider cabinet.",
            "The owner confirms any paid number, subscription or outbound-call costs.",
        ],
        "notes": ["API availability does not guarantee that a particular number or service is available in every country."],
    },
    "mango_office": {
        "name": "MANGO OFFICE",
        "setup_mode": "api_and_manual",
        "api_adapter_status": "guide_only",
        "api_available": True,
        "api_operations": [
            "MANGO OFFICE publishes separate API references for Virtual PBX, dialogs and other products.",
            "The correct API product and methods depend on the customer's enabled services; this MCP guide does not perform provider writes.",
        ],
        "manual_steps": [
            "The customer administrator enables the required MANGO OFFICE service and API access.",
            "The administrator supplies API credentials through the provider's approved secure channel.",
            "The operator configures SIP devices, extensions, call groups, routes and event subscriptions in the cabinet.",
            "The customer confirms any paid numbers, seats or call packages before activation.",
        ],
        "notes": ["Do not assume one API key or one endpoint covers every MANGO OFFICE product."],
    },
    "asterisk": {
        "name": "Asterisk / ARI",
        "setup_mode": "api_and_manual",
        "api_adapter_status": "guide_only",
        "api_available": True,
        "api_operations": [
            "Asterisk ARI exposes REST operations and asynchronous events over WebSocket.",
            "This MCP does not yet manage Asterisk configuration or ARI channels directly.",
        ],
        "manual_steps": [
            "The PBX administrator enables the HTTP server and configures a dedicated ARI user.",
            "The administrator restricts access by network policy and enables HTTPS/WSS with valid TLS certificates.",
            "The administrator configures PJSIP endpoints, trunks, dialplan and Stasis routing.",
            "The operator receives a dedicated least-privilege ARI endpoint and credentials outside chat logs.",
        ],
        "notes": ["ARI being enabled is not equivalent to a configured SIP trunk; PBX and dialplan setup remain customer/operator tasks."],
    },
    "freepbx": {
        "name": "FreePBX",
        "setup_mode": "manual_or_version_specific_api",
        "api_adapter_status": "not_implemented",
        "api_available": None,
        "api_operations": [],
        "manual_steps": [
            "The administrator confirms the FreePBX version, enabled modules and supported management interfaces.",
            "The administrator configures trunks, extensions, inbound/outbound routes and firewall rules.",
            "The administrator enables and secures Asterisk ARI only when the selected workflow requires it.",
            "The operator tests registration and call routing using a test extension before live traffic.",
        ],
        "notes": ["Available APIs and module behavior vary by FreePBX release and installed modules; do not assume an ARI or REST API is enabled."],
    },
    "elevenlabs": {
        "name": "ElevenLabs Conversational AI",
        "setup_mode": "api_and_manual",
        "api_adapter_status": "existing_guarded_tools_plus_external_connector",
        "api_available": True,
        "api_operations": [
            "The current MCP has guarded outbound-call and Scribe transcription operations.",
            "Agent configuration, number import and workspace management can be performed through the customer's authorized ElevenLabs connector/API.",
        ],
        "manual_steps": [
            "The customer supplies an ElevenLabs workspace/API key with only the required permissions.",
            "The customer or operator creates/chooses an agent and configures its prompt, language, tools and privacy settings.",
            "The customer imports or connects the carrier number through SIP trunk settings.",
            "Configure the carrier's SIP destination, transport, authentication or IP ACL according to the provider.",
            "Make a real call only after the customer approves the destination, billing and explicit test window.",
        ],
        "notes": [
            "SIP trunking connects an existing PBX/carrier to the voice agent; it does not provide a phone number by itself.",
            "UDP is documented as experimental for ElevenLabs; TCP or TLS is preferred for production.",
        ],
    },
}

_CHANNEL_GUIDES: dict[str, dict[str, str]] = {
    "amo_chat": {
        "title": "amoCRM Chat API",
        "execution": "manual",
        "manual": "Register the chat channel with amoCRM/support, obtain channel scope and secret, then configure the signed webhook and Chat API credentials.",
    },
    "whatsapp": {
        "title": "WhatsApp",
        "execution": "manual",
        "manual": "The customer connects its WhatsApp Business/official provider account, completes required Meta/provider checks and approves templates and conversation billing.",
    },
    "telegram": {
        "title": "Telegram",
        "execution": "manual",
        "manual": "The customer creates/owns the Telegram bot, supplies the token through a secure channel and authorizes the selected amoCRM/provider connector.",
    },
    "instagram": {
        "title": "Instagram",
        "execution": "manual",
        "manual": "The customer connects the required Instagram professional account and Meta business assets, then authorizes the CRM channel.",
    },
    "website": {
        "title": "Website forms/chat",
        "execution": "manual",
        "manual": "The operator installs the approved form/chat widget or webhook on the customer's website and verifies test-lead delivery.",
    },
    "email": {
        "title": "Email",
        "execution": "manual",
        "manual": "The customer authorizes the mailbox/provider and confirms sender, reply and inbound-mail routing.",
    },
}

_PIPELINE_TEMPLATES: dict[str, list[str]] = {
    "hotel": ["Новая бронь", "Уточнение деталей", "Ожидает подтверждения", "Подтверждена", "Заселение", "Завершено"],
    "dental": ["Новая заявка", "Связаться с пациентом", "Запись", "Первичный приём", "План лечения", "Завершено"],
    "service": ["Новая заявка", "Первичный контакт", "Квалифицирован", "Оценка/смета", "В работе", "Завершено"],
    "retail": ["Новая заявка", "Консультация", "Предложение", "Ожидает оплаты", "Оплачено", "Завершено"],
    "education": ["Новая заявка", "Консультация", "Пробное занятие", "Ожидает оплаты", "Обучение", "Завершено"],
    "manufacturing": ["Новая заявка", "Техническая консультация", "Подготовка КП", "Согласование", "Производство", "Отгрузка", "Завершено"],
    "real_estate": ["Новая заявка", "Уточнение потребности", "Подбор объектов", "Показ", "Переговоры", "Сделка завершена"],
    "generic": ["Новая заявка", "Первичный контакт", "Квалификация", "Предложение", "Переговоры", "Успешно реализовано"],
}

_ALLOWED_HOST_LABEL = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")


def get_provider_catalog() -> dict[str, dict[str, Any]]:
    """Return a copy of provider capability metadata; no secrets or connections."""
    return {
        provider: {
            **details,
            "api_operations": list(details["api_operations"]),
            "manual_steps": list(details["manual_steps"]),
            "notes": list(details["notes"]),
        }
        for provider, details in _PROVIDER_CATALOG.items()
    }


def build_client_setup_plan(
    business_type: str,
    telephony_provider: str,
    requested_channels: list[str],
) -> dict[str, Any]:
    """Create a non-persistent onboarding plan for one customer account."""
    if not isinstance(business_type, str) or not business_type.strip():
        raise ValueError("business_type is required")
    business = business_type.strip().lower().replace("-", "_").replace(" ", "_")
    if not isinstance(telephony_provider, str) or telephony_provider not in _PROVIDER_CATALOG:
        raise ValueError("Unsupported telephony provider")
    if not isinstance(requested_channels, list):
        raise ValueError("requested_channels must be a list")
    channels: list[str] = []
    for channel in requested_channels:
        if not isinstance(channel, str) or channel not in _CHANNEL_GUIDES:
            raise ValueError("Unsupported channel")
        if channel not in channels:
            channels.append(channel)

    provider = _PROVIDER_CATALOG[telephony_provider]
    statuses = _PIPELINE_TEMPLATES.get(business, _PIPELINE_TEMPLATES["generic"])
    steps: list[dict[str, Any]] = [
        {
            "id": "connect_amocrm",
            "title": "Подключить amoCRM клиента",
            "execution": "manual",
            "details": "Клиент/администратор устанавливает OAuth-интеграцию и подтверждает доступ через /connect.",
        },
        {
            "id": "audit_account",
            "title": "Проверить аккаунт и структуру CRM",
            "execution": "mcp_read_only",
            "details": "Выполнить get_amocrm_setup_report; проверить воронки, пользователей, поля, источники и вебхуки.",
        },
        {
            "id": "prepare_pipeline",
            "title": "Подготовить воронку продаж",
            "execution": "mcp_preview_then_confirmed_write",
            "details": "Сначала согласовать шаблон, затем создать его через create_pipeline после отдельного разрешения на запись.",
        },
        {
            "id": "telephony_manual",
            "title": "Подключить телефонию и SIP",
            "execution": "manual",
            "details": "Использовать руководство выбранного провайдера; не передавать SIP-пароли в переписку или MCP-параметры.",
            "provider": telephony_provider,
            "provider_setup_mode": provider["setup_mode"],
            "provider_api_adapter_status": provider["api_adapter_status"],
        },
    ]
    for channel in channels:
        guide = _CHANNEL_GUIDES[channel]
        steps.append({
            "id": "channel_" + channel,
            "title": "Подключить канал: " + guide["title"],
            "execution": guide["execution"],
            "details": guide["manual"],
        })
    steps.extend([
        {
            "id": "test_integrations",
            "title": "Проверить интеграции",
            "execution": "mcp_diagnostics_plus_manual_test",
            "details": "Проверить вебхуки, тестовые лиды и настройки каналов; реальные сообщения/звонки выполнять только после подтверждения.",
        },
        {
            "id": "handover",
            "title": "Передать систему клиенту",
            "execution": "manual_checklist",
            "details": "Передать ключи и права владельцу, проверить биллинг и постоянные интеграции, затем отключить локальную OAuth-связь MCP.",
        },
    ])
    return {
        "business_type": business,
        "telephony_provider": telephony_provider,
        "requested_channels": channels,
        "suggested_pipeline": {"name": "Продажи", "statuses": list(statuses)},
        "provider_guidance": {
            "setup_mode": provider["setup_mode"],
            "api_adapter_status": provider["api_adapter_status"],
            "manual_steps": list(provider["manual_steps"]),
            "notes": list(provider["notes"]),
        },
        "steps": steps,
        "persistence": "none",
        "writes_performed": False,
    }


def validate_sip_endpoint(host: str, port: int, transport: str) -> dict[str, Any]:
    """Validate SIP endpoint parameters without resolving DNS or storing credentials."""
    if not isinstance(host, str) or not host.strip():
        raise ValueError("SIP host is required")
    value = host.strip()
    if any(ch.isspace() for ch in value) or "://" in value or any(ch in value for ch in "/@?#"):
        raise ValueError("SIP host must be a hostname or IP address only (no URI, userinfo, path or query)")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("SIP port must be an integer from 1 to 65535")
    if not isinstance(transport, str) or transport.strip().lower() not in {"tcp", "tls", "udp"}:
        raise ValueError("SIP transport must be tcp, tls or udp")

    normalized_host = value.lower()
    ip_value = value[1:-1] if value.startswith("[") and value.endswith("]") else value
    try:
        ipaddress.ip_address(ip_value)
        normalized_host = ip_value.lower()
    except ValueError:
        if value.startswith("[") or value.endswith("]") or len(normalized_host) > 253:
            raise ValueError("SIP host is not a valid hostname or IP address")
        labels = normalized_host.rstrip(".").split(".")
        if not labels or any(not _ALLOWED_HOST_LABEL.fullmatch(label) for label in labels):
            raise ValueError("SIP host is not a valid hostname or IP address")
        normalized_host = normalized_host.rstrip(".")

    protocol = transport.strip().lower()
    warning = None
    if protocol == "udp":
        warning = (
            "UDP may be experimental for some voice-AI SIP providers; verify provider support "
            "and prefer TCP or TLS for production."
        )
    return {
        "host": normalized_host,
        "port": port,
        "transport": protocol,
        "warning": warning,
    }
