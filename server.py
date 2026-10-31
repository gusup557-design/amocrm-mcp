import os
import json
import re
import time
import uuid
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from oauth_backend import provider, register_amo_routes, amo_access_token, db
from language_support import SUPPORTED_LANGUAGES, get_language_profile, resolve_language
from chat_api import AmoChatApiClient
from transcription import transcribe_source_url
from voice_telephony import start_outbound_call
from webhook_security import verify_amocrm_chat_signature, verify_elevenlabs_signature
from webhook_events import build_webhook_event_identity
from conversation_automation import build_post_call_action_plan
from connection_lifecycle import ensure_disconnect_confirmation, public_connection_summaries
from provisioning import build_client_setup_plan, get_provider_catalog as build_provider_catalog, validate_sip_endpoint

# Конфигурация
AMOCRM_DOMAIN = os.environ.get("AMOCRM_DOMAIN", "").strip()
AMOCRM_TOKEN = os.environ.get("AMOCRM_TOKEN", "").strip()
if AMOCRM_DOMAIN and not re.fullmatch(r"[A-Za-z0-9-]+", AMOCRM_DOMAIN):
    raise RuntimeError("AMOCRM_DOMAIN must be a subdomain without protocol or path")
BASE_URL = f"https://{AMOCRM_DOMAIN}.amocrm.ru/api/v4" if AMOCRM_DOMAIN else ""

_vercel_hosts = {"amocrm-mcp-ascan-006.vercel.app", os.environ.get("VERCEL_URL", "").strip()}
_allowed_hosts = []
for _host in _vercel_hosts:
    if _host:
        _allowed_hosts.extend([_host, f"{_host}:*"])

auth_settings = AuthSettings(
    issuer_url="https://amocrm-mcp-ascan-006.vercel.app",
    resource_server_url="https://amocrm-mcp-ascan-006.vercel.app/mcp",
    required_scopes=["crm"],
    validate_token_resource=True,
    client_registration_options=ClientRegistrationOptions(
        enabled=True,
        valid_scopes=["crm"],
        default_scopes=["crm"],
    ),
)
mcp = FastMCP(
    "amoCRM",
    auth_server_provider=provider,
    auth=auth_settings,
    transport_security=TransportSecuritySettings(allowed_hosts=_allowed_hosts),
)


async def get_headers():
    token, domain = await amo_access_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }, f"https://{domain}/api/v4"


async def api_get(path: str, params: dict = None) -> dict:
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("Invalid amoCRM API path")
    headers, base_url = await get_headers()
    async with httpx.AsyncClient(verify=True, timeout=20.0, follow_redirects=False) as client:
        resp = await client.get(f"{base_url}{path}", headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()


async def api_post(path: str, data: dict) -> dict:
    if os.environ.get("MCP_ALLOW_WRITE", "false").lower() != "true":
        raise PermissionError("CRM write operations are disabled by default")
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("Invalid amoCRM API path")
    headers, base_url = await get_headers()
    async with httpx.AsyncClient(verify=True, timeout=20.0, follow_redirects=False) as client:
        resp = await client.post(f"{base_url}{path}", headers=headers, json=data)
        resp.raise_for_status()
        return resp.json()


async def api_patch(path: str, data: dict) -> dict:
    if os.environ.get("MCP_ALLOW_WRITE", "false").lower() != "true":
        raise PermissionError("CRM write operations are disabled by default")
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("Invalid amoCRM API path")
    headers, base_url = await get_headers()
    async with httpx.AsyncClient(verify=True, timeout=20.0, follow_redirects=False) as client:
        resp = await client.patch(f"{base_url}{path}", headers=headers, json=data)
        resp.raise_for_status()
        return resp.json()


async def api_delete(path: str):
    if os.environ.get("MCP_ALLOW_WRITE", "false").lower() != "true":
        raise PermissionError("CRM write operations are disabled by default")
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("Invalid amoCRM API path")
    headers, base_url = await get_headers()
    async with httpx.AsyncClient(verify=True, timeout=20.0, follow_redirects=False) as client:
        resp = await client.delete(f"{base_url}{path}", headers=headers)
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return {"status":"deleted"}
        return resp.json()


# ===================== АККАУНТ =====================

@mcp.tool()
async def get_account_info() -> str:
    """Получить информацию об аккаунте amoCRM"""
    data = await api_get("/account", params={"with": "amojo_id,amojo_rights,users_groups,task_types,version,entity_names,datetime_settings"})
    return json.dumps(data, ensure_ascii=False, indent=2)


# ===================== СДЕЛКИ (LEADS) =====================

@mcp.tool()
async def get_leads(page: int = 1, limit: int = 50, query: str = "", order_by: str = "updated_at", order_dir: str = "desc") -> str:
    """Получить список сделок (лидов). query — поиск по названию. order_by — поле сортировки (created_at, updated_at, id). order_dir — направление (asc/desc). По умолчанию сортировка по updated_at desc (свежие первыми)."""
    params = {"page": page, "limit": limit}
    if query:
        params["query"] = query
    if order_by:
        params[f"order[{order_by}]"] = order_dir
    data = await api_get("/leads", params=params)
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_lead(lead_id: int) -> str:
    """Получить детали конкретной сделки по ID."""
    data = await api_get(f"/leads/{lead_id}", params={"with": "contacts,catalog_elements,loss_reason"})
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool()
async def create_lead(name: str, price: int = 0, status_id: int = 0, pipeline_id: int = 0) -> str:
    """Создать новую сделку. name — название, price — бюджет, status_id — ID статуса, pipeline_id — ID воронки."""
    lead = {"name": name}
    if price:
        lead["price"] = price
    if status_id:
        lead["status_id"] = status_id
    if pipeline_id:
        lead["pipeline_id"] = pipeline_id
    data = await api_post("/leads", [lead])
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool()
async def update_lead(lead_id: int, name: str = "", price: int = -1, status_id: int = 0) -> str:
    """Обновить сделку. lead_id — ID сделки, остальные поля — что обновить."""
    lead = {"id": lead_id}
    if name:
        lead["name"] = name
    if price >= 0:
        lead["price"] = price
    if status_id:
        lead["status_id"] = status_id
    data = await api_patch("/leads", [lead])
    return json.dumps(data, ensure_ascii=False, indent=2)


# ===================== КОНТАКТЫ =====================

@mcp.tool()
async def get_contacts(page: int = 1, limit: int = 50, query: str = "", order_by: str = "updated_at", order_dir: str = "desc") -> str:
    """Получить список контактов. query — поиск по имени/телефону/email. order_by — поле сортировки (created_at, updated_at, id). order_dir — направление (asc/desc). По умолчанию сортировка по updated_at desc (свежие первыми)."""
    params = {"page": page, "limit": limit}
    if query:
        params["query"] = query
    if order_by:
        params[f"order[{order_by}]"] = order_dir
    data = await api_get("/contacts", params=params)
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_contact(contact_id: int) -> str:
    """Получить детали контакта по ID."""
    data = await api_get(f"/contacts/{contact_id}", params={"with": "leads,customers,catalog_elements"})
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool()
async def create_contact(first_name: str, last_name: str = "", phone: str = "", email: str = "") -> str:
    """Создать контакт. first_name — имя, last_name — фамилия, phone — телефон, email — email."""
    contact = {"first_name": first_name}
    if last_name:
        contact["last_name"] = last_name
    custom_fields = []
    if phone:
        custom_fields.append({"field_code": "PHONE", "values": [{"value": phone}]})
    if email:
        custom_fields.append({"field_code": "EMAIL", "values": [{"value": email}]})
    if custom_fields:
        contact["custom_fields_values"] = custom_fields
    data = await api_post("/contacts", [contact])
    return json.dumps(data, ensure_ascii=False, indent=2)


# ===================== КОМПАНИИ =====================

@mcp.tool()
async def get_companies(page: int = 1, limit: int = 50, query: str = "", order_by: str = "updated_at", order_dir: str = "desc") -> str:
    """Получить список компаний. query — поиск по названию. order_by — поле сортировки (created_at, updated_at, id). order_dir — направление (asc/desc). По умолчанию сортировка по updated_at desc (свежие первыми)."""
    params = {"page": page, "limit": limit}
    if query:
        params["query"] = query
    if order_by:
        params[f"order[{order_by}]"] = order_dir
    data = await api_get("/companies", params=params)
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_company(company_id: int) -> str:
    """Получить детали компании по ID."""
    data = await api_get(f"/companies/{company_id}", params={"with": "contacts,leads,catalog_elements"})
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool()
async def create_company(name: str) -> str:
    """Создать компанию. name — название компании."""
    data = await api_post("/companies", [{"name": name}])
    return json.dumps(data, ensure_ascii=False, indent=2)


# ===================== ЗАДАЧИ =====================

@mcp.tool()
async def get_tasks(page: int = 1, limit: int = 50, order_by: str = "updated_at", order_dir: str = "desc") -> str:
    """Получить список задач. order_by — поле сортировки (created_at, updated_at, id, complete_till). order_dir — направление (asc/desc). По умолчанию сортировка по updated_at desc (свежие первыми)."""
    params = {"page": page, "limit": limit}
    if order_by:
        params[f"order[{order_by}]"] = order_dir
    data = await api_get("/tasks", params=params)
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool()
async def create_task(text: str, complete_till: int, entity_id: int = 0, entity_type: str = "leads", task_type_id: int = 1) -> str:
    """Создать задачу. text — текст, complete_till — дедлайн (unix timestamp), entity_id — ID привязанной сущности, entity_type — тип (leads/contacts/companies), task_type_id — тип задачи (1=звонок, 2=встреча, 3=письмо)."""
    task = {
        "text": text,
        "complete_till": complete_till,
        "task_type_id": task_type_id,
    }
    if entity_id:
        task["entity_id"] = entity_id
        task["entity_type"] = entity_type
    data = await api_post("/tasks", [task])
    return json.dumps(data, ensure_ascii=False, indent=2)


# ===================== ВОРОНКИ =====================

@mcp.tool()
async def get_pipelines() -> str:
    """Получить список воронок и их этапов."""
    data = await api_get("/leads/pipelines")
    return json.dumps(data, ensure_ascii=False, indent=2)


# ===================== ПОЛЬЗОВАТЕЛИ =====================

@mcp.tool()
async def get_users() -> str:
    """Получить список пользователей аккаунта."""
    data = await api_get("/users")
    return json.dumps(data, ensure_ascii=False, indent=2)


# ===================== ПРИМЕЧАНИЯ =====================

@mcp.tool()
async def add_note(entity_type: str, entity_id: int, text: str) -> str:
    """Добавить примечание к сущности. entity_type — leads/contacts/companies, entity_id — ID сущности, text — текст примечания."""
    if entity_type not in {"leads", "contacts", "companies"}:
        raise ValueError("entity_type must be leads, contacts, or companies")
    if entity_id <= 0:
        raise ValueError("entity_id must be positive")
    note = {
        "note_type": "common",
        "params": {"text": text}
    }
    data = await api_post(f"/{entity_type}/{entity_id}/notes", [note])
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_notes(entity_type: str, entity_id: int) -> str:
    """Получить примечания сущности. entity_type — leads/contacts/companies, entity_id — ID."""
    if entity_type not in {"leads", "contacts", "companies"}:
        raise ValueError("entity_type must be leads, contacts, or companies")
    if entity_id <= 0:
        raise ValueError("entity_id must be positive")
    data = await api_get(f"/{entity_type}/{entity_id}/notes")
    return json.dumps(data, ensure_ascii=False, indent=2)


# ===================== РАСШИРЕННОЕ УПРАВЛЕНИЕ CRM =====================

def _dump(data):
    return json.dumps(data, ensure_ascii=False, indent=2)

def _json_arg(value: str, expected_type):
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("Передан некорректный JSON") from exc
    if not isinstance(parsed, expected_type):
        raise ValueError("JSON имеет неверный тип")
    return parsed


@mcp.tool()
async def list_amocrm_connections() -> str:
    """Показать подключённые к MCP аккаунты amoCRM без токенов и секретов."""
    rows = await db(
        "GET",
        "amocrm_connections",
        params={"select": "account_id,base_domain,expires_at", "order": "account_id.asc", "limit": "100"},
    )
    return _dump({
        "connected_accounts": public_connection_summaries(rows),
        "active_account_policy": "exactly_one",
        "requires_disconnect_before_switch": True,
    })


@mcp.tool()
async def disconnect_amocrm_connection(account_id: int, confirm_disconnect: bool = False) -> str:
    """Удалить локально сохранённые OAuth-данные одного аккаунта MCP. Не удаляет интеграцию в amoCRM."""
    if isinstance(account_id, bool) or account_id <= 0:
        raise ValueError("account_id must be a positive integer")
    ensure_disconnect_confirmation(confirm_disconnect)
    deleted = await db(
        "DELETE",
        "amocrm_connections",
        params={"account_id": "eq." + str(account_id)},
        prefer="return=representation",
    )
    if not deleted:
        raise LookupError("No MCP connection found for the supplied account_id")
    return _dump({
        "account_id": account_id,
        "mcp_oauth_credentials_removed": True,
        "amoCRM_integration_revoked": False,
        "manual_next_step": (
            "If access should be fully removed, uninstall or revoke this MCP integration "
            "in the customer's amoCRM account. Confirm any other client-owned integrations "
            "remain installed before handing the account back."
        ),
    })


@mcp.tool()
async def get_provider_catalog() -> str:
    """Получить каталог телефонии и разделение API-возможностей и ручных действий."""
    return _dump(build_provider_catalog())


@mcp.tool()
async def get_telephony_provider_guide(provider: str) -> str:
    """Получить пошаговую инструкцию для конкретного SIP/телефонного провайдера."""
    catalog = build_provider_catalog()
    if provider not in catalog:
        raise ValueError("Unsupported telephony provider")
    return _dump(catalog[provider])


@mcp.tool()
async def get_client_setup_plan(
    business_type: str,
    telephony_provider: str,
    requested_channels_json: str = "[]",
) -> str:
    """Сформировать план настройки клиента без сохранения профиля и без изменения сервисов."""
    channels = _json_arg(requested_channels_json, list)
    return _dump(build_client_setup_plan(
        business_type=business_type,
        telephony_provider=telephony_provider,
        requested_channels=channels,
    ))


@mcp.tool()
async def validate_sip_endpoint_settings(host: str, port: int, transport: str) -> str:
    """Проверить формат SIP-хоста, порта и транспорта; проверка не соединяется с сервером."""
    return _dump(validate_sip_endpoint(host, port, transport))


@mcp.tool()
async def get_amocrm_setup_report() -> str:
    """Провести read-only аудит подключённой amoCRM: аккаунт, воронки, пользователи, поля, вебхуки и каналы."""
    connections = await db(
        "GET",
        "amocrm_connections",
        params={"select": "account_id,base_domain,expires_at", "order": "account_id.asc", "limit": "100"},
    )
    safe_connections = public_connection_summaries(connections)
    if not safe_connections:
        return _dump({
            "status": "not_connected",
            "message": "Connect one customer account through /connect first.",
            "checks": {},
            "writes_performed": False,
        })
    if len(safe_connections) != 1:
        return _dump({
            "status": "ambiguous_connection",
            "connected_accounts": safe_connections,
            "message": "Disconnect all but one account before running the CRM audit.",
            "checks": {},
            "writes_performed": False,
        })

    account_data = None
    checks = {}

    async def inspect(name: str, path: str, params: dict | None = None) -> None:
        try:
            data = await api_get(path, params)
            if name == "account":
                account = data.get("account", data) if isinstance(data, dict) else {}
                checks[name] = {"status": "ok"}
                nonlocal account_data
                account_data = {
                    key: account[key]
                    for key in ("id", "name", "subdomain", "currency", "timezone")
                    if isinstance(account, dict) and key in account
                }
                return
            total = data.get("_total_items") if isinstance(data, dict) else None
            embedded = data.get("_embedded", {}) if isinstance(data, dict) else {}
            if not isinstance(total, int):
                arrays = [value for value in embedded.values() if isinstance(value, list)] if isinstance(embedded, dict) else []
                total = len(arrays[0]) if arrays else 0
            checks[name] = {"status": "ok", "count": total}
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            checks[name] = {
                "status": "error",
                "error_type": type(exc).__name__,
                "http_status": status_code,
            }

    audits = [
        ("account", "/account", {"with": "amojo_id,amojo_rights,users_groups,task_types,version,entity_names,datetime_settings"}),
        ("pipelines", "/leads/pipelines", {"limit": 250}),
        ("users", "/users", {"limit": 250}),
        ("lead_fields", "/leads/custom_fields", {"limit": 250}),
        ("contact_fields", "/contacts/custom_fields", {"limit": 250}),
        ("company_fields", "/companies/custom_fields", {"limit": 250}),
        ("sources", "/sources", {"limit": 250}),
        ("webhooks", "/webhooks", {"limit": 100}),
        ("widgets", "/widgets", {"limit": 250}),
        ("catalogs", "/catalogs", {"limit": 250}),
    ]
    for name, path, params in audits:
        await inspect(name, path, params)

    successful = sum(1 for value in checks.values() if value["status"] == "ok")
    failed = len(checks) - successful
    return _dump({
        "status": "ready_for_review" if failed == 0 else "needs_attention",
        "connected_account": safe_connections[0],
        "account": account_data,
        "checks": checks,
        "summary": {"passed": successful, "failed": failed, "total": len(checks)},
        "write_mode_enabled": os.environ.get("MCP_ALLOW_WRITE", "false").lower() == "true",
        "writes_performed": False,
        "manual_follow_up": [
            "Confirm provider and channel ownership with the customer.",
            "Inspect API permissions and account-specific feature availability.",
            "Do not run paid calls or send external messages until the customer approves a test.",
        ],
    })


@mcp.tool()
async def get_salesbots(page: int = 1, limit: int = 100) -> str:
    """Получить список Salesbot и состояние активности. Только чтение."""
    return _dump(await api_get("/bots", {"page": page, "limit": min(max(limit, 1), 250)}))


@mcp.tool()
async def get_salesbot(bot_id: int) -> str:
    """Получить конфигурацию Salesbot по ID. Только чтение."""
    if bot_id <= 0:
        raise ValueError("bot_id must be positive")
    return _dump(await api_get(f"/bots/{bot_id}"))


@mcp.tool()
async def get_talks(page: int = 1, limit: int = 100, status: str = "", contact_id: int = 0, origin: str = "") -> str:
    """Получить список бесед/чатов и их статусы. Содержимое сообщений может требовать отдельного Chat API."""
    params = {"page": page, "limit": min(max(limit, 1), 250)}
    if status:
        params["status"] = status
    if contact_id > 0:
        params["contact_id"] = contact_id
    if origin:
        params["origin"] = origin
    return _dump(await api_get("/talks", params))


@mcp.tool()
async def get_talk(talk_id: int) -> str:
    """Получить сведения о конкретной беседе, контакте и связанной сделке."""
    if talk_id <= 0:
        raise ValueError("talk_id must be positive")
    return _dump(await api_get(f"/talks/{talk_id}"))


@mcp.tool()
async def get_custom_fields(entity_type: str) -> str:
    """Получить пользовательские поля leads, contacts или companies."""
    if entity_type not in {"leads", "contacts", "companies"}:
        raise ValueError("entity_type must be leads, contacts, or companies")
    return _dump(await api_get(f"/{entity_type}/custom_fields", {"limit": 250}))


@mcp.tool()
async def get_webhooks() -> str:
    """Получить список установленных вебхуков. Требуются права администратора."""
    return _dump(await api_get("/webhooks"))


@mcp.tool()
async def get_sources() -> str:
    """Получить источники лидов и подключённые каналы аккаунта. Требуются права администратора."""
    return _dump(await api_get("/sources"))


@mcp.tool()
async def get_amma_agents(page: int = 1, limit: int = 50) -> str:
    """Получить список ИИ-агентов Аммы, созданных этой интеграцией. Нужен отдельный scope «Амма» и доступность Аммы на тарифе."""
    return _dump(await api_get("/amma/agents", {"page": page, "limit": min(max(limit, 1), 50)}))


@mcp.tool()
async def create_pipeline(name: str, statuses_json: str = "[]") -> str:
    """Создать воронку с этапами. Изменяет CRM; требует MCP_ALLOW_WRITE=true и прав администратора. statuses_json — JSON-массив объектов этапов."""
    statuses = _json_arg(statuses_json, list)
    payload = {"name": name}
    if statuses:
        payload["_embedded"] = {"statuses": statuses}
    return _dump(await api_post("/leads/pipelines", [payload]))


@mcp.tool()
async def update_pipeline(pipeline_id: int, name: str = "", is_main: bool = False) -> str:
    """Изменить название или основной статус воронки. Изменяет CRM; требует MCP_ALLOW_WRITE=true и прав администратора."""
    if pipeline_id <= 0:
        raise ValueError("pipeline_id must be positive")
    item = {"id": pipeline_id}
    if name:
        item["name"] = name
    if is_main:
        item["is_main"] = True
    if len(item) == 1:
        raise ValueError("Укажи новое name или is_main=true")
    return _dump(await api_patch("/leads/pipelines", [item]))


@mcp.tool()
async def add_call_record(phone: str, duration: int, direction: str, source: str, link: str = "", call_result: str = "", call_status: int = 0, responsible_user_id: int = 0) -> str:
    """Записать завершённый входящий/исходящий звонок в карточку контакта по номеру. Это не инициирует реальный звонок; требует MCP_ALLOW_WRITE=true."""
    if direction not in {"inbound", "outbound"}:
        raise ValueError("direction must be inbound or outbound")
    if duration < 0 or not phone.strip() or not source.strip():
        raise ValueError("phone/source are required and duration cannot be negative")
    call = {"phone": phone, "duration": duration, "direction": direction, "source": source}
    if link:
        call["link"] = link
    if call_result:
        call["call_result"] = call_result
    if call_status:
        if call_status not in range(1, 8):
            raise ValueError("call_status must be from 1 to 7")
        call["call_status"] = call_status
    if responsible_user_id > 0:
        call["responsible_user_id"] = responsible_user_id
    return _dump(await api_post("/calls", [call]))


@mcp.tool()
async def create_webhook(destination: str, events_json: str) -> str:
    """Подписать amoCRM на события и отправлять их на HTTPS URL. Изменяет настройки интеграции; требует MCP_ALLOW_WRITE=true и прав администратора."""
    from urllib.parse import urlparse
    parsed = urlparse(destination)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("destination must be a valid HTTPS URL")
    events = _json_arg(events_json, list)
    if not events or not all(isinstance(x, str) for x in events):
        raise ValueError("events_json must be a non-empty JSON array of strings")
    return _dump(await api_post("/webhooks", {"destination": destination, "settings": events}))


@mcp.tool()
async def create_amma_agent(name: str, description: str, system_prompt: str, ai_instructions: str = "", model_size: str = "M") -> str:
    """Создать ИИ-агента Аммы, подключённого к этому MCP. Нужен scope «Амма» (только технический аккаунт amoCRM), доступность Аммы и MCP_ALLOW_WRITE=true."""
    if model_size not in {"S", "M", "L"}:
        raise ValueError("model_size must be S, M, or L")
    agent = {
        "name": name, "description": description, "system_prompt": system_prompt,
        "ai_instructions": ai_instructions, "model_size": model_size,
        "mcp": {"url": "https://amocrm-mcp-ascan-006.vercel.app/mcp", "transport": "streamable-http"},
        "is_active": True,
    }
    return _dump(await api_post("/amma/agents", [agent]))


@mcp.tool()
async def get_events(page: int = 1, limit: int = 100, entity: str = "", entity_id: int = 0, created_after: int = 0) -> str:
    """Получить историю событий CRM: создание и изменения сущностей. Поддерживает фильтр по типу сущности, ID и времени."""
    params = {"page": page, "limit": min(max(limit, 1), 100)}
    if entity:
        if entity not in {"lead", "contact", "company", "customer", "task"} and not re.fullmatch(r"catalog_\d+", entity):
            raise ValueError("Unsupported entity filter")
        params["filter[entity]"] = entity
    if entity_id > 0:
        if not entity:
            raise ValueError("entity is required when entity_id is provided")
        params["filter[entity_id]"] = entity_id
    if created_after > 0:
        params["filter[created_at]"] = created_after
    return _dump(await api_get("/events", params))


@mcp.tool()
async def get_widgets(page: int = 1, limit: int = 100) -> str:
    """Получить список доступных, загруженных и установленных виджетов аккаунта."""
    return _dump(await api_get("/widgets", {"page": page, "limit": min(max(limit, 1), 250)}))


@mcp.tool()
async def get_catalogs(page: int = 1, limit: int = 100) -> str:
    """Получить каталоги/списки amoCRM, доступные текущему пользователю."""
    return _dump(await api_get("/catalogs", {"page": page, "limit": min(max(limit, 1), 250)}))


@mcp.tool()
async def get_catalog_elements(catalog_id: int, page: int = 1, limit: int = 100, query: str = "") -> str:
    """Получить элементы указанного каталога, с поиском по заполненным полям."""
    if catalog_id <= 0:
        raise ValueError("catalog_id must be positive")
    params = {"page": page, "limit": min(max(limit, 1), 250)}
    if query:
        params["query"] = query
    return _dump(await api_get(f"/catalogs/{catalog_id}/elements", params))


@mcp.tool()
async def get_tags(entity_type: str = "leads", page: int = 1, limit: int = 100, query: str = "") -> str:
    """Получить теги сделок, контактов, компаний или покупателей."""
    if entity_type not in {"leads", "contacts", "companies", "customers"}:
        raise ValueError("Unsupported entity_type")
    params = {"page": page, "limit": min(max(limit, 1), 250)}
    if query:
        params["query"] = query
    return _dump(await api_get(f"/{entity_type}/tags", params))


@mcp.tool()
async def get_chat_templates(page: int = 1, limit: int = 50, with_reviews: bool = False) -> str:
    """Получить шаблоны сообщений чатов, включая статусы модерации WhatsApp при необходимости."""
    params = {"page": page, "limit": min(max(limit, 1), 50)}
    if with_reviews:
        params["with"] = "reviews"
    return _dump(await api_get("/chats/templates", params))


@mcp.tool()
async def get_amma_agent(agent_id: str) -> str:
    """Получить настройки агента Аммы по UUID, включая system_prompt и ai_instructions. Требуется scope Амма."""
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", agent_id):
        raise ValueError("agent_id must be a UUID")
    return _dump(await api_get(f"/amma/agents/{agent_id}"))


@mcp.tool()
async def update_amma_agent(agent_id: str, patch_json: str) -> str:
    """Обновить агента Аммы (имя, промпты, модель, MCP endpoint, активность). Требуется scope Амма и MCP_ALLOW_WRITE=true."""
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", agent_id):
        raise ValueError("agent_id must be a UUID")
    patch = _json_arg(patch_json, dict)
    allowed = {"name", "description", "ai_instructions", "system_prompt", "avatar", "model_size", "mcp", "is_active"}
    if not patch or set(patch) - allowed:
        raise ValueError("patch_json contains no fields or unsupported fields")
    return _dump(await api_patch(f"/amma/agents/{agent_id}", patch))


@mcp.tool()
async def delete_amma_agent(agent_id: str) -> str:
    """Удалить агента Аммы, созданного этой интеграцией. Необратимо; требуется scope Амма и MCP_ALLOW_WRITE=true."""
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", agent_id):
        raise ValueError("agent_id must be a UUID")
    return _dump(await api_delete(f"/amma/agents/{agent_id}"))


@mcp.tool()
async def delete_pipeline(pipeline_id: int) -> str:
    """Удалить пустую воронку. Необратимо; amoCRM запрещает удалять последнюю воронку и воронку со сделками."""
    if pipeline_id <= 0:
        raise ValueError("pipeline_id must be positive")
    return _dump(await api_delete(f"/leads/pipelines/{pipeline_id}"))


def _chat_api_client() -> AmoChatApiClient:
    return AmoChatApiClient(
        scope_id=os.environ.get("AMOCHAT_SCOPE_ID", "").strip(),
        secret=os.environ.get("AMOCHAT_CHANNEL_SECRET", "").strip(),
        base_url=os.environ.get("AMOCHAT_BASE_URL", "https://amojo.amocrm.ru").strip(),
    )


@mcp.tool()
async def chat_get_history(conversation_id: str, offset: int = 0, limit: int = 50) -> str:
    """Получить историю сообщений чата через amoCRM Chat API. Нужны scope_id и секрет канала."""
    data = await _chat_api_client().get_history(
        conversation_id=conversation_id,
        offset=offset,
        limit=limit,
    )
    return _dump(data)


@mcp.tool()
async def chat_send_text_message(
    conversation_id: str,
    receiver_id: str,
    receiver_name: str,
    message_text: str,
    silent: bool = False,
) -> str:
    """Отправить текстовое сообщение в чат amoCRM. Запись заблокирована, пока MCP_ALLOW_WRITE не установлен в true."""
    if os.environ.get("MCP_ALLOW_WRITE", "false").lower() != "true":
        raise PermissionError("Chat API write operations are disabled by default")
    required = {
        "AMOCHAT_BOT_CLIENT_ID": os.environ.get("AMOCHAT_BOT_CLIENT_ID", "").strip(),
        "AMOCHAT_BOT_REF_ID": os.environ.get("AMOCHAT_BOT_REF_ID", "").strip(),
        "AMOCHAT_BOT_NAME": os.environ.get("AMOCHAT_BOT_NAME", "").strip(),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError("Missing Chat API bot configuration: " + ", ".join(missing))
    if not conversation_id.strip() or not receiver_id.strip() or not receiver_name.strip() or not message_text.strip():
        raise ValueError("conversation_id, receiver_id, receiver_name and message_text are required")
    now = time.time()
    payload = {
        "event_type": "new_message",
        "payload": {
            "timestamp": int(now),
            "msec_timestamp": int(now * 1000),
            "msgid": "veb-" + str(uuid.uuid4()),
            "conversation_id": conversation_id,
            "sender": {
                "id": required["AMOCHAT_BOT_CLIENT_ID"],
                "name": required["AMOCHAT_BOT_NAME"],
                "ref_id": required["AMOCHAT_BOT_REF_ID"],
            },
            "receiver": {"id": receiver_id, "name": receiver_name},
            "message": {"type": "text", "text": message_text},
            "silent": silent,
        },
    }
    return _dump(await _chat_api_client().send_message(payload))


@mcp.tool()
async def transcription_transcribe_audio_url(
    audio_url: str,
    language: str = "",
    diarize: bool = True,
    tag_audio_events: bool = True,
) -> str:
    """Транскрибировать запись звонка через ElevenLabs Scribe v2. Требуются API key, allowlist доменов и MCP_ALLOW_PAID_AI=true."""
    result = await transcribe_source_url(
        audio_url=audio_url,
        language=language,
        diarize=diarize,
        tag_audio_events=tag_audio_events,
    )
    return _dump(result)


@mcp.tool()
async def voice_start_outbound_call(
    to_number: str,
    confirm_call: bool = False,
    crm_contact_id: int = 0,
    preferred_language: str = "",
) -> str:
    """Начать исходящий AI-звонок через ElevenLabs SIP с необязательной CRM-корреляцией. Требуются allowlist номера, включённые платные операции и явное confirm_call=true."""
    result = await start_outbound_call(
        to_number=to_number,
        confirm_call=confirm_call,
        crm_contact_id=crm_contact_id or None,
        preferred_language=preferred_language,
    )
    return _dump(result)


@mcp.tool()
async def get_supported_languages() -> str:
    """Получить языки диалогов V1: русский, кыргызский, казахский и узбекский."""
    return _dump(list(SUPPORTED_LANGUAGES.values()))


@mcp.tool()
async def resolve_conversation_language(
    preferred_language: str = "",
    detected_language: str = "",
    fallback_language: str = "",
) -> str:
    """Выбрать язык диалога: предпочтение контакта, распознанный язык, резервный язык, затем русский."""
    resolved = resolve_language(
        preferred_language=preferred_language or None,
        detected_language=detected_language or None,
        fallback_language=fallback_language or None,
    )
    return _dump(get_language_profile(resolved))


@mcp.tool()
async def conversation_preview_post_call_actions(event_id: str) -> str:
    """Preview CRM note/task proposals from a stored completed voice call. Read-only; never mutates CRM."""
    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("event_id is required")
    rows = await db(
        "GET",
        "communication_webhook_events",
        params={
            "provider": "eq.elevenlabs",
            "event_id": "eq." + event_id.strip(),
            "select": "raw_payload,event_type,processing_status",
            "limit": "1",
        },
    )
    if not rows:
        raise ValueError("Completed call event was not found")
    payload = rows[0].get("raw_payload")
    return _dump(build_post_call_action_plan(payload))


@mcp.custom_route("/webhooks/amo-chat", methods=["POST"])
async def receive_amocrm_chat_webhook(request: Request) -> JSONResponse:
    """Authenticate and idempotently persist an amoCRM Chat API event."""
    raw_body = await request.body()
    if len(raw_body) > 262144:
        return JSONResponse({"error": "payload_too_large"}, status_code=413)
    secret = os.environ.get("AMOCHAT_CHANNEL_SECRET", "").strip()
    signature = request.headers.get("X-Signature", "")
    if not verify_amocrm_chat_signature(raw_body, signature, secret):
        return JSONResponse({"error": "invalid_signature"}, status_code=401)
    try:
        payload = json.loads(raw_body)
        provider_name, event_type, event_id, conversation_id = build_webhook_event_identity(
            "amocrm_chat", payload, raw_body
        )
    except (json.JSONDecodeError, ValueError, TypeError):
        return JSONResponse({"error": "invalid_payload"}, status_code=400)
    try:
        await db(
            "POST",
            "communication_webhook_events",
            params={"on_conflict": "provider,event_id"},
            payload={
                "provider": provider_name,
                "event_id": event_id,
                "event_type": event_type,
                "conversation_id": conversation_id,
                "raw_payload": payload,
                "processing_status": "received",
            },
            prefer="resolution=ignore-duplicates,return=minimal",
        )
    except Exception:
        return JSONResponse({"error": "event_persistence_failed"}, status_code=503)
    return JSONResponse({"status": "accepted"})


@mcp.custom_route("/webhooks/elevenlabs", methods=["POST"])
async def receive_elevenlabs_webhook(request: Request) -> JSONResponse:
    """Authenticate and idempotently persist ElevenLabs post-call events."""
    raw_body = await request.body()
    if len(raw_body) > 1048576:
        return JSONResponse({"error": "payload_too_large"}, status_code=413)
    secret = os.environ.get("ELEVENLABS_WEBHOOK_SECRET", "").strip()
    signature = request.headers.get("ElevenLabs-Signature", "")
    if not verify_elevenlabs_signature(raw_body, signature, secret):
        return JSONResponse({"error": "invalid_signature"}, status_code=401)
    try:
        payload = json.loads(raw_body)
        provider_name, event_type, event_id, conversation_id = build_webhook_event_identity(
            "elevenlabs", payload, raw_body
        )
    except (json.JSONDecodeError, ValueError, TypeError):
        return JSONResponse({"error": "invalid_payload"}, status_code=400)
    if event_type not in {"post_call_transcription", "call_initiation_failure"}:
        return JSONResponse({"error": "unsupported_event_type"}, status_code=400)
    try:
        await db(
            "POST",
            "communication_webhook_events",
            params={"on_conflict": "provider,event_id"},
            payload={
                "provider": provider_name,
                "event_id": event_id,
                "event_type": event_type,
                "conversation_id": conversation_id,
                "raw_payload": payload,
                "processing_status": "received",
            },
            prefer="resolution=ignore-duplicates,return=minimal",
        )
    except Exception:
        return JSONResponse({"error": "event_persistence_failed"}, status_code=503)
    return JSONResponse({"status": "accepted"})


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Non-sensitive liveness/readiness check; never returns credentials or CRM records."""
    supabase_status = "not_configured"
    supabase_url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    supabase_key = (
        os.environ.get("SUPABASE_SECRET_KEY", "").strip()
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    )
    if supabase_url and supabase_key:
        headers = {"apikey": supabase_key, "Accept-Profile": "public"}
        # Legacy service_role keys are JWTs; new sb_secret keys must be sent as apikey only.
        if supabase_key.count(".") == 2:
            headers["Authorization"] = f"Bearer {supabase_key}"
        try:
            async with httpx.AsyncClient(verify=True, timeout=8.0, follow_redirects=False) as client:
                response = await client.get(
                    f"{supabase_url}/rest/v1/amocrm_connections?select=account_id&limit=1",
                    headers=headers,
                )
            supabase_status = "connected" if response.is_success else f"error_{response.status_code}"
        except httpx.HTTPError:
            supabase_status = "unreachable"
    amo_status = "not_connected"
    try:
        amo_rows = await db("GET", "amocrm_connections", params={"select":"account_id","limit":"1"})
        if amo_rows:
            amo_status = "connected"
    except Exception:
        pass
    return JSONResponse({
        "status": "ok",
        "service": "amoCRM MCP",
        "tools": 47,
        "supabase": supabase_status,
        "amoCRM": amo_status,
    })


register_amo_routes(mcp)
app = mcp.streamable_http_app()

if __name__ == "__main__":
    mcp.run(transport="stdio")
