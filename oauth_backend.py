"""OAuth persistence and amoCRM connection helpers for the remote MCP server."""
import base64, hashlib, hmac, json, os, secrets, time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode, urlparse

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from mcp.server.auth.provider import (
    AccessToken, AuthorizationCode, AuthorizationParams, OAuthAuthorizationServerProvider,
    RefreshToken, RegistrationError, TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, PlainTextResponse

BASE = "https://amocrm-mcp-ascan-006.vercel.app"
AMO_REDIRECT = os.getenv("AMOCRM_REDIRECT_URI", BASE + "/oauth/callback")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = (os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()

def _key():
    raw = os.getenv("MCP_TOKEN_ENCRYPTION_KEY", "")
    if len(raw) != 64:
        raise RuntimeError("MCP_TOKEN_ENCRYPTION_KEY must be 64 hex characters")
    return bytes.fromhex(raw)

def encrypt(value: str) -> str:
    nonce = secrets.token_bytes(12)
    return base64.urlsafe_b64encode(nonce + AESGCM(_key()).encrypt(nonce, value.encode(), None)).decode()

def decrypt(value: str) -> str:
    raw = base64.urlsafe_b64decode(value.encode())
    return AESGCM(_key()).decrypt(raw[:12], raw[12:], None).decode()

def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()

async def db(method: str, table: str, *, params=None, payload=None, prefer=None):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase is not configured")
    headers = {"apikey": SUPABASE_KEY, "Accept-Profile": "public", "Content-Profile": "public"}
    if SUPABASE_KEY.count(".") == 2:
        headers["Authorization"] = "Bearer " + SUPABASE_KEY
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if prefer:
        headers["Prefer"] = prefer
    async with httpx.AsyncClient(timeout=12, verify=True, follow_redirects=False) as c:
        r = await c.request(method, f"{SUPABASE_URL}/rest/v1/{table}", headers=headers, params=params, json=payload)
        r.raise_for_status()
        if r.status_code == 204 or not r.content:
            return []
        return r.json()

def _json(v):
    return json.dumps(v, separators=(",", ":"), ensure_ascii=False)

class SupabaseOAuthProvider(OAuthAuthorizationServerProvider):
    """MCP OAuth Authorization Code + PKCE provider backed by Supabase."""
    async def get_client(self, client_id):
        rows = await db("GET", "mcp_oauth_clients", params={"client_id": "eq."+client_id, "select":"*","limit":"1"})
        if not rows: return None
        row = rows[0]
        meta = row["client_info"]
        if isinstance(meta, str): meta = json.loads(meta)
        if row.get("client_secret_enc"):
            meta["client_secret"] = decrypt(row["client_secret_enc"])
        return OAuthClientInformationFull.model_validate(meta)

    async def register_client(self, client_info):
        data = client_info.model_dump(mode="json", exclude_none=True)
        client_id = data["client_id"]
        secret = data.pop("client_secret", None)
        enc = encrypt(secret) if secret else None
        await db("POST","mcp_oauth_clients",payload={"client_id":client_id,"client_secret_enc":enc,"client_info":data},prefer="resolution=merge-duplicates,return=minimal")

    async def authorize(self, client, params: AuthorizationParams) -> str:
        sid = secrets.token_urlsafe(32)
        payload = {
            "state": params.state, "scopes": params.scopes or ["crm"],
            "code_challenge": params.code_challenge, "redirect_uri": str(params.redirect_uri),
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
            "resource": expected_resource, "client_id": client.client_id,
        }
        await db("POST","mcp_oauth_pending",payload={"transaction_id":sid,"client_id":client.client_id,"payload":payload,"expires_at":(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()},prefer="return=minimal")
        return BASE + "/oauth/consent?" + urlencode({"session":sid})

    async def load_authorization_code(self, client, code):
        rows=await db("GET","mcp_oauth_authorization_codes",params={"code_hash":"eq."+digest(code),"client_id":"eq."+str(client.client_id),"select":"*","limit":"1"})
        if not rows: return None
        p=rows[0]["payload"]
        if isinstance(p,str): p=json.loads(p)
        return AuthorizationCode.model_validate(p)

    async def exchange_authorization_code(self, client, authorization_code):
        code=authorization_code.code
        await db("DELETE","mcp_oauth_authorization_codes",params={"code_hash":"eq."+digest(code)})
        access=secrets.token_urlsafe(48); refresh=secrets.token_urlsafe(48)
        exp=int(time.time())+3600
        payload={"client_id":client.client_id,"scopes":authorization_code.scopes,"expires_at":exp,"resource":authorization_code.resource}
        await db("POST","mcp_oauth_tokens",payload=[
            {"token_hash":digest(access),"client_id":client.client_id,"token_type":"access","payload":payload,"expires_at":datetime.fromtimestamp(exp,timezone.utc).isoformat()},
            {"token_hash":digest(refresh),"client_id":client.client_id,"token_type":"refresh","payload":{"client_id":client.client_id,"scopes":authorization_code.scopes,"resource":authorization_code.resource},"expires_at":(datetime.now(timezone.utc)+timedelta(days=30)).isoformat()}
        ],prefer="return=minimal")
        return OAuthToken(access_token=access,refresh_token=refresh,expires_in=3600,scope=" ".join(authorization_code.scopes))

    async def load_refresh_token(self, client, token):
        rows=await db("GET","mcp_oauth_tokens",params={"token_hash":"eq."+digest(token),"token_type":"eq.refresh","revoked_at":"is.null","expires_at":"gt."+datetime.now(timezone.utc).isoformat(),"select":"*","limit":"1"})
        if not rows: return None
        p=rows[0]["payload"]
        if isinstance(p,str): p=json.loads(p)
        return RefreshToken(token=token,client_id=rows[0]["client_id"],scopes=p["scopes"],resource=p.get("resource"))

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        await db("PATCH","mcp_oauth_tokens",params={"token_hash":"eq."+digest(refresh_token.token)},payload={"revoked_at":datetime.now(timezone.utc).isoformat()},prefer="return=minimal")
        access=secrets.token_urlsafe(48); refresh=secrets.token_urlsafe(48); exp=int(time.time())+3600
        payload={"client_id":client.client_id,"scopes":scopes,"expires_at":exp}
        await db("POST","mcp_oauth_tokens",payload=[
            {"token_hash":digest(access),"client_id":client.client_id,"token_type":"access","payload":payload,"expires_at":datetime.fromtimestamp(exp,timezone.utc).isoformat()},
            {"token_hash":digest(refresh),"client_id":client.client_id,"token_type":"refresh","payload":{"client_id":client.client_id,"scopes":scopes},"expires_at":(datetime.now(timezone.utc)+timedelta(days=30)).isoformat()}
        ],prefer="return=minimal")
        return OAuthToken(access_token=access,refresh_token=refresh,expires_in=3600,scope=" ".join(scopes))

    async def load_access_token(self, token):
        rows=await db("GET","mcp_oauth_tokens",params={"token_hash":"eq."+digest(token),"token_type":"eq.access","revoked_at":"is.null","select":"*","limit":"1"})
        if not rows: return None
        p=rows[0]["payload"]
        if isinstance(p,str): p=json.loads(p)
        if p.get("expires_at",0) <= int(time.time()): return None
        return AccessToken(token=token,client_id=rows[0]["client_id"],scopes=p["scopes"],expires_at=p["expires_at"],resource=p.get("resource"))

    async def verify_token(self, token):
        return await self.load_access_token(token)

    async def revoke_token(self, token):
        token_value = token.token
        await db("PATCH","mcp_oauth_tokens",params={"token_hash":"eq."+digest(token_value)},payload={"revoked_at":datetime.now(timezone.utc).isoformat()},prefer="return=minimal")

provider = SupabaseOAuthProvider()

async def amo_access_token():
    rows=await db("GET","amocrm_connections",params={"select":"*","limit":"1"})
    if not rows: raise RuntimeError("amoCRM is not connected. Open /connect first.")
    row=rows[0]
    expiry=datetime.fromisoformat(row["expires_at"].replace("Z","+00:00"))
    if expiry > datetime.now(timezone.utc)+timedelta(minutes=3):
        return decrypt(row["access_token_enc"]), row["base_domain"]
    # Atomic lock prevents parallel refresh-token rotation.
    lock=await db("POST","rpc/claim_amocrm_refresh_lock",payload={"p_account_id":row["account_id"],"p_lock_seconds":45})
    if lock is not True and lock != [{"claim_amocrm_refresh_lock":True}]:
        await __import__("asyncio").sleep(1)
        rows=await db("GET","amocrm_connections",params={"account_id":"eq."+str(row["account_id"]),"select":"*","limit":"1"})
        row=rows[0]
        expiry=datetime.fromisoformat(row["expires_at"].replace("Z","+00:00"))
        if expiry <= datetime.now(timezone.utc)+timedelta(minutes=1):
            raise RuntimeError("amoCRM token refresh is already running; retry shortly")
        return decrypt(row["access_token_enc"]),row["base_domain"]
    client_id=row["client_id"]; client_secret=decrypt(row["client_secret_enc"]); refresh=decrypt(row["refresh_token_enc"])
    async with httpx.AsyncClient(timeout=20,verify=True,follow_redirects=False) as c:
        r=await c.post(f"https://{row['base_domain']}/oauth2/access_token",json={"client_id":client_id,"client_secret":client_secret,"grant_type":"refresh_token","refresh_token":refresh,"redirect_uri":AMO_REDIRECT})
        r.raise_for_status(); tok=r.json()
    await db("PATCH","amocrm_connections",params={"account_id":"eq."+str(row["account_id"])},payload={
        "access_token_enc":encrypt(tok["access_token"]),"refresh_token_enc":encrypt(tok["refresh_token"]),
        "expires_at":datetime.fromtimestamp(time.time()+int(tok["expires_in"]),timezone.utc).isoformat(),
        "refresh_lock_until":None
    },prefer="return=minimal")
    return tok["access_token"],row["base_domain"]

def register_amo_routes(mcp):
    @mcp.custom_route("/connect",methods=["GET"])
    async def connect(request: Request):
        state=secrets.token_hex(24)
        await db("POST","amocrm_oauth_pending",payload={"state":state,"client_id":"pending","client_secret_enc":"pending","expires_at":(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat()},prefer="resolution=merge-duplicates,return=minimal")
        html=f"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Подключение amoCRM</title><style>body{{font:16px system-ui;background:#f5f7fb;display:grid;place-items:center;min-height:90vh}}main{{background:white;padding:32px;border-radius:16px;max-width:520px;box-shadow:0 8px 40px #14213d18}}a{{display:inline-block;padding:14px 20px;background:#2563eb;color:white;border-radius:10px;text-decoration:none}}small{{color:#555}}</style></head><body><main><h1>Подключить amoCRM</h1><p>Разрешите интеграции доступ к CRM. Токены будут храниться зашифрованными в базе данных.</p><p><script class="amocrm_oauth" charset="utf-8" data-name="VEB amoCRM MCP" data-description="Доступ ChatGPT к amoCRM через защищённый MCP-сервер" data-redirect_uri="{AMO_REDIRECT}" data-secrets_uri="{BASE}/oauth/secrets" data-scopes="crm" data-title="Подключить amoCRM" data-color="default" data-state="{state}" data-mode="popup" src="https://www.amocrm.ru/auth/button.min.js"></script></p><small>После подтверждения вернитесь сюда. Окно можно закрыть после сообщения об успехе.</small></main></body></html>"""
        return HTMLResponse(html,headers={"Cache-Control":"no-store"})

    @mcp.custom_route("/oauth/secrets",methods=["POST"])
    async def amo_secrets(request: Request):
        try: body=await request.json()
        except Exception: body=dict(await request.form())
        state=str(body.get("state") or "")
        cid=str(body.get("client_id") or "")
        secret=str(body.get("client_secret") or "")
        if not state or not cid or not secret: return JSONResponse({"error":"invalid_payload"},status_code=400)
        rows=await db("GET","amocrm_oauth_pending",params={"state":"eq."+state,"select":"state,expires_at","limit":"1"})
        if not rows or datetime.fromisoformat(rows[0]["expires_at"].replace("Z","+00:00")) < datetime.now(timezone.utc):
            return JSONResponse({"error":"invalid_or_expired_state"},status_code=400)
        await db("PATCH","amocrm_oauth_pending",params={"state":"eq."+state},payload={"client_id":cid,"client_secret_enc":encrypt(secret)},prefer="return=minimal")
        return JSONResponse({"status":"stored"})

    @mcp.custom_route("/oauth/callback",methods=["GET"])
    async def amo_callback(request: Request):
        q=request.query_params
        if q.get("error"): return HTMLResponse("<h2>Авторизация amoCRM отклонена</h2>",status_code=400)
        state=q.get("state",""); code=q.get("code",""); referer=q.get("referer","")
        if not state or not code or not referer: return HTMLResponse("<h2>Не хватает параметров OAuth callback</h2>",status_code=400)
        rows=await db("GET","amocrm_oauth_pending",params={"state":"eq."+state,"select":"*","limit":"1"})
        if not rows or rows[0]["client_id"]=="pending": return HTMLResponse("<h2>Данные интеграции не получены. Повторите подключение.</h2>",status_code=400)
        pending=rows[0]
        host=urlparse(referer if "://" in referer else "https://"+referer).hostname
        if not host or not (host.endswith(".amocrm.ru") or host.endswith(".amocrm.com") or host.endswith(".kommo.com")):
            return HTMLResponse("<h2>Недопустимый домен аккаунта</h2>",status_code=400)
        domain=host
        async with httpx.AsyncClient(timeout=20,verify=True,follow_redirects=False) as c:
            r=await c.post(f"https://{domain}/oauth2/access_token",json={"client_id":pending["client_id"],"client_secret":decrypt(pending["client_secret_enc"]),"grant_type":"authorization_code","code":code,"redirect_uri":AMO_REDIRECT})
            r.raise_for_status(); tok=r.json()
            a=await c.get(f"https://{domain}/api/v4/account",headers={"Authorization":"Bearer "+tok["access_token"]})
            a.raise_for_status(); account=a.json()
        await db("POST","amocrm_connections",payload={"account_id":account["id"],"base_domain":domain,"client_id":pending["client_id"],"client_secret_enc":pending["client_secret_enc"],"access_token_enc":encrypt(tok["access_token"]),"refresh_token_enc":encrypt(tok["refresh_token"]),"expires_at":datetime.fromtimestamp(time.time()+int(tok["expires_in"]),timezone.utc).isoformat()},prefer="resolution=merge-duplicates,return=minimal")
        await db("DELETE","amocrm_oauth_pending",params={"state":"eq."+state})
        return HTMLResponse("<!doctype html><html><meta charset=utf-8><h2>amoCRM подключена</h2><p>Токены сохранены в зашифрованном виде. Можно закрыть это окно.</p></html>")

    @mcp.custom_route("/oauth/consent",methods=["GET","POST"])
    async def consent(request: Request):
        sid=request.query_params.get("session") or (await request.form()).get("session")
        if not sid: return PlainTextResponse("Missing session",status_code=400)
        rows=await db("GET","mcp_oauth_pending",params={"transaction_id":"eq."+str(sid),"select":"*","limit":"1"})
        if not rows or datetime.fromisoformat(rows[0]["expires_at"].replace("Z","+00:00")) < datetime.now(timezone.utc):
            return PlainTextResponse("Authorization session expired",status_code=400)
        if request.method=="GET":
            html=f"""<!doctype html><html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Разрешение доступа</title><style>body{{font:16px system-ui;background:#f5f7fb;display:grid;place-items:center;min-height:90vh}}main{{background:white;padding:30px;border-radius:16px;max-width:480px}}input,button{{font:inherit;padding:12px;width:100%;margin:8px 0;box-sizing:border-box}}button{{background:#2563eb;color:white;border:0;border-radius:8px}}</style><main><h2>Разрешить ChatGPT доступ к amoCRM?</h2><p>Сервер выдаст доступ к подключённому аккаунту CRM. Введите пароль владельца сервера для подтверждения.</p><form method=post><input type=hidden name=session value="{sid}"><input type=password name=password required autocomplete=current-password placeholder="Пароль владельца"><button>Разрешить доступ</button></form></main></html>"""
            return HTMLResponse(html,headers={"Cache-Control":"no-store"})
        form=await request.form()
        expected=os.getenv("MCP_ADMIN_PASSWORD","")
        supplied=str(form.get("password") or "")
        if not expected or not hmac.compare_digest(expected,supplied):
            return HTMLResponse("<h3>Неверный пароль или пароль владельца не настроен.</h3>",status_code=401)
        p=rows[0]["payload"]
        if isinstance(p,str): p=json.loads(p)
        client=await provider.get_client(p["client_id"])
        if not client: return PlainTextResponse("Unknown OAuth client",status_code=400)
        code=secrets.token_urlsafe(32)
        auth=AuthorizationCode(code=code,scopes=p["scopes"],expires_at=time.time()+180,client_id=p["client_id"],code_challenge=p["code_challenge"],redirect_uri=p["redirect_uri"],redirect_uri_provided_explicitly=p["redirect_uri_provided_explicitly"],resource=p.get("resource"))
        await db("POST","mcp_oauth_authorization_codes",payload={"code_hash":digest(code),"client_id":p["client_id"],"payload":auth.model_dump(mode="json"),"expires_at":datetime.fromtimestamp(auth.expires_at,timezone.utc).isoformat()},prefer="return=minimal")
        await db("DELETE","mcp_oauth_pending",params={"transaction_id":"eq."+sid})
        return RedirectResponse(auth.redirect_uri+"?"+urlencode({"code":code,"state":p.get("state") or ""}),status_code=302,headers={"Cache-Control":"no-store"})
