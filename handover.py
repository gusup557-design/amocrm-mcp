"""Customer handover readiness checklist; evidence is operator-attested, not remote-verified."""

from __future__ import annotations

from typing import Any


HANDOVER_CHECKS: dict[str, str] = {
    "customer_admin_access": "Клиент получил собственные права администратора amoCRM.",
    "client_owned_provider_accounts": "Телефония, номера и внешние сервисы зарегистрированы на клиента.",
    "client_keys_transferred": "Ключи и секреты переданы владельцу безопасным способом.",
    "sip_inbound_routing_tested": "Входящий звонок проверен на согласованном тестовом номере.",
    "sip_outbound_routing_tested": "Исходящий звонок проверен с разрешённым направлением и бюджетом.",
    "chat_channels_tested": "Подключённые каналы сообщений проверены тестовыми событиями.",
    "amo_webhooks_verified": "Вебхуки amoCRM проверены и ведут на нужные клиентские сервисы.",
    "automation_reviewed": "Автоматизации согласованы, ограничения и ответственные определены.",
    "billing_confirmed": "Клиент подтвердил тарифы, стоимость номеров, вызовов и AI-операций.",
    "privacy_retention_disclosed": "Клиенту объяснены запись звонков, доступ к транскриптам и сроки хранения данных.",
    "client_admin_owns_integrations": "Клиент понимает, какие интеграции оставить активными и какие отозвать.",
    "mcp_local_credentials_disconnected": "Временные OAuth-учётные данные удалены из MCP после передачи.",
}


def build_client_handover_checklist(completed_checks: list[str]) -> dict[str, Any]:
    """Build a checklist from operator assertions without contacting external services."""
    if not isinstance(completed_checks, list):
        raise ValueError("completed_checks must be a list")
    for item in completed_checks:
        if not isinstance(item, str) or item not in HANDOVER_CHECKS:
            raise ValueError("Unknown handover check")

    completed = list(dict.fromkeys(completed_checks))
    missing = [key for key in HANDOVER_CHECKS if key not in completed]
    return {
        "status": "ready_for_handover" if not missing else "incomplete",
        "ready_for_handover": not missing,
        "completed_count": len(completed),
        "required_count": len(HANDOVER_CHECKS),
        "missing_count": len(missing),
        "completed_checks": completed,
        "missing_checks": missing,
        "checklist": [
            {
                "id": key,
                "description": description,
                "completed": key in completed,
            }
            for key, description in HANDOVER_CHECKS.items()
        ],
        "operator_attestation_only": True,
        "verification_limit": (
            "Checklist entries are operator attestations and are not independently verified "
            "against external provider dashboards, phone call records or customer signatures."
        ),
        "writes_performed": False,
    }
