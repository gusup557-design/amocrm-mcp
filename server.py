import os
import json
import re
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from oauth_backend import provider, register_amo_routes, amo_access_token, db

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
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("Invalid amoCRM API path")
    headers, base_url = await get_headers()
    async with httpx.AsyncClient(verify=True, timeout=20.0, follow_redirects=False) as client:
        resp = await client.post(f"{base_url}{path}", headers=headers, json=data)
        resp.raise_for_status()
        return resp.json()


async def api_patch(path: str, data: dict) -> dict:
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("Invalid amoCRM API path")
    headers, base_url = await get_headers()
    async with httpx.AsyncClient(verify=True, timeout=20.0, follow_redirects=False) as client:
        resp = await client.patch(f"{base_url}{path}", headers=headers, json=data)
        resp.raise_for_status()
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
        "tools": 17,
        "supabase": supabase_status,
        "amoCRM": amo_status,
    })


register_amo_routes(mcp)
app = mcp.streamable_http_app()

if __name__ == "__main__":
    mcp.run(transport="stdio")
