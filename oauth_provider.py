"""Persistent OAuth 2.1 provider for the amoCRM MCP server.

All OAuth state is stored in Supabase. Raw bearer tokens are never stored:
only SHA-256 hashes are persisted. The owner password is supplied through
MCP_AUTH_PASSWORD and must be set as a sensitive Vercel environment variable.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from pydantic import AnyHttpUrl
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

BASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
)
OWNER_PASSWORD = os.environ.get("MCP_AUTH_PASSWORD", "")
ISSUER = "https://amocrm-mcp-ascan-006.vercel.app"
SCOPE = "crm:read"


def _headers() -> dict[str, str]:
    if not BASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase server credentials are not configured")
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
        "Accept-Profile": "public",
        "Content-Profile": "public",
        "Prefer": "return=representation",
    }
    if SUPABASE_KEY.count(".") == 2:
        headers["Authorization"] = f"Bearer {SUPABASE_KEY}"
    return headers


async def _request(method: str, table: str, *, params: dict[str, str] | None = None,
                   payload: Any = None, prefer: str | None = None) -> Any:
    headers = _headers()
    if prefer:
        headers["Prefer"] = prefer
    async with httpx.AsyncClient(verify=True, timeout=12.0, follow_redirects=False) as client:
        response = await client.request(
            method, f"{BASE_URL}/rest/v1/{table}", headers=headers,
            params=params, json=payload,
        )
    response.raise_for_status()
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _client_from(row: dict[str, Any]) -> OAuthClientInformationFull:
    return OAuthClientInformationFull.model_validate(row["client_info"])


class SupabaseOAuthProvider(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    def __init__(self, issuer: str = ISSUER):
        self.issuer = issuer.rstrip("/")

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        rows = await _request("GET", "mcp_oauth_clients",
                              params={"client_id": f"eq.{client_id}", "select": "client_info", "limit": "1"})
        return _client_from(rows[0]) if rows else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            raise ValueError("OAuth client id is missing")
        await _request("POST", "mcp_oauth_clients", payload={
            "client_id": client_info.client_id,
            "client_info": client_info.model_dump(mode="json"),
        }, prefer="resolution=merge-duplicates,return=minimal")

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        if not client.client_id:
            raise HTTPException(400, "Invalid OAuth client")
        if SCOPE not in (params.scopes or []):
            raise HTTPException(400, "Required scope crm:read was not requested")
        if not OWNER_PASSWORD:
            raise HTTPException(503, "MCP_AUTH_PASSWORD is not configured")
        transaction = secrets.token_urlsafe(32)
        payload = {
            "client_id": client.client_id,
            "redirect_uri": str(params.redirect_uri),
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
            "code_challenge": params.code_challenge,
            "state": params.state,
            "scopes": params.scopes or [SCOPE],
            "resource": params.resource,
        }
        await _request("POST", "mcp_oauth_pending", payload={
            "transaction_id": transaction,
            "client_id": client.client_id,
            "payload": payload,
            "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 600)),
        })
        return f"{self.issuer}/oauth/login?{urlencode({'transaction': transaction})}"

    async def login_page(self, transaction: str) -> HTMLResponse:
        rows = await _request("GET", "mcp_oauth_pending", params={
            "transaction_id": f"eq.{transaction}", "select": "transaction_id", "expires_at": f"gt.{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}", "limit": "1"
        })
        if not rows:
            raise HTTPException(400, "Authorization request expired or invalid")
        safe_txn = html.escape(transaction, quote=True)
        page = f"""<!doctype html><html lang="ru"><meta charset="utf-8">
<title>Авторизация amoCRM MCP</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{{font:16px system-ui;max-width:440px;margin:10vh auto;padding:24px;background:#111827;color:#f9fafb}}
form{{display:grid;gap:14px}}input,button{{font:inherit;padding:12px;border-radius:8px;border:1px solid #4b5563}}
input{{background:#1f2937;color:white}}button{{background:#2563eb;color:white;border:0;cursor:pointer}}</style>
<h2>Доступ к amoCRM через MCP</h2><p>Подтвердите вход владельца сервера. Пароль хранится только в переменной окружения сервера.</p>
<form method="post" action="/oauth/approve">
<input type="hidden" name="transaction" value="{safe_txn}">
<label>Пароль владельца<input type="password" name="password" autocomplete="current-password" required></label>
<button type="submit">Разрешить доступ</button></form></html>"""
        return HTMLResponse(page, headers={"Cache-Control": "no-store"})

    async def approve(self, request: Request) -> Response:
        form = await request.form()
        transaction = form.get("transaction")
        password = form.get("password")
        if not isinstance(transaction, str) or not isinstance(password, str):
            raise HTTPException(400, "Invalid form")
        if not OWNER_PASSWORD or not secrets.compare_digest(password, OWNER_PASSWORD):
            raise HTTPException(401, "Неверный пароль")
        rows = await _request("GET", "mcp_oauth_pending", params={
            "transaction_id": f"eq.{transaction}", "select": "*",
            "expires_at": f"gt.{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}", "limit": "1"
        })
        if not rows:
            raise HTTPException(400, "Authorization request expired or invalid")
        row = rows[0]
        data = row["payload"]
        client = await self.get_client(data["client_id"])
        if not client:
            raise HTTPException(400, "OAuth client no longer exists")
        code = "mcp_" + secrets.token_urlsafe(32)
        auth_code = AuthorizationCode(
            code=code, client_id=data["client_id"],
            redirect_uri=AnyHttpUrl(data["redirect_uri"]),
            redirect_uri_provided_explicitly=bool(data["redirect_uri_provided_explicitly"]),
            expires_at=time.time() + 300,
            scopes=data.get("scopes") or [SCOPE],
            code_challenge=data["code_challenge"],
            resource=data.get("resource"), subject="amoCRM-owner",
        )
        await _request("POST", "mcp_oauth_authorization_codes", payload={
            "code_hash": _hash(code), "client_id": data["client_id"],
            "payload": auth_code.model_dump(mode="json"),
            "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(auth_code.expires_at)),
        })
        await _request("DELETE", "mcp_oauth_pending", params={"transaction_id": f"eq.{transaction}"})
        redirect = construct_redirect_uri(
            data["redirect_uri"], code=code, state=data.get("state")
        )
        return RedirectResponse(redirect, status_code=302, headers={"Cache-Control": "no-store"})

    async def load_authorization_code(self, client: OAuthClientInformationFull,
                                      authorization_code: str) -> AuthorizationCode | None:
        rows = await _request("GET", "mcp_oauth_authorization_codes", params={
            "code_hash": f"eq.{_hash(authorization_code)}", "client_id": f"eq.{client.client_id}",
            "select": "payload,expires_at", "limit": "1",
        })
        if not rows:
            return None
        if rows[0]["expires_at"] <= time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()):
            return None
        return AuthorizationCode.model_validate(rows[0]["payload"])

    async def exchange_authorization_code(self, client: OAuthClientInformationFull,
                                          authorization_code: AuthorizationCode) -> OAuthToken:
        await _request("DELETE", "mcp_oauth_authorization_codes",
                       params={"code_hash": f"eq.{_hash(authorization_code.code)}"})
        return await self._issue_tokens(client.client_id or "", authorization_code.scopes,
                                        authorization_code.resource, authorization_code.subject)

    async def _issue_tokens(self, client_id: str, scopes: list[str],
                            resource: str | None, subject: str | None) -> OAuthToken:
        access = "mcp_at_" + secrets.token_urlsafe(40)
        refresh = "mcp_rt_" + secrets.token_urlsafe(40)
        now = int(time.time())
        access_obj = AccessToken(token=access, client_id=client_id, scopes=scopes,
                                 expires_at=now + 3600, resource=resource, subject=subject)
        refresh_obj = RefreshToken(token=refresh, client_id=client_id, scopes=scopes,
                                   expires_at=now + 30 * 86400, subject=subject)
        await _request("POST", "mcp_oauth_tokens", payload=[
            {"token_hash": _hash(access), "token_type": "access", "client_id": client_id,
             "payload": access_obj.model_dump(mode="json"),
             "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 3600))},
            {"token_hash": _hash(refresh), "token_type": "refresh", "client_id": client_id,
             "payload": refresh_obj.model_dump(mode="json"),
             "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 30 * 86400))},
        ])
        return OAuthToken(access_token=access, refresh_token=refresh, expires_in=3600,
                          scope=" ".join(scopes))

    async def load_access_token(self, token: str) -> AccessToken | None:
        rows = await _request("GET", "mcp_oauth_tokens", params={
            "token_hash": f"eq.{_hash(token)}", "token_type": "eq.access",
            "revoked_at": "is.null", "select": "payload,expires_at", "limit": "1",
        })
        if not rows:
            return None
        if rows[0]["expires_at"] and rows[0]["expires_at"] <= time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()):
            return None
        return AccessToken.model_validate(rows[0]["payload"])

    async def load_refresh_token(self, client: OAuthClientInformationFull,
                                 refresh_token: str) -> RefreshToken | None:
        rows = await _request("GET", "mcp_oauth_tokens", params={
            "token_hash": f"eq.{_hash(refresh_token)}", "token_type": "eq.refresh",
            "client_id": f"eq.{client.client_id}", "revoked_at": "is.null",
            "select": "payload,expires_at", "limit": "1",
        })
        if not rows:
            return None
        return RefreshToken.model_validate(rows[0]["payload"])

    async def exchange_refresh_token(self, client: OAuthClientInformationFull,
                                     refresh_token: RefreshToken, scopes: list[str]) -> OAuthToken:
        await _request("DELETE", "mcp_oauth_tokens",
                       params={"token_hash": f"eq.{_hash(refresh_token.token)}"})
        return await self._issue_tokens(client.client_id or "", scopes, None, refresh_token.subject)

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        await _request("PATCH", "mcp_oauth_tokens",
                       params={"token_hash": f"eq.{_hash(token.token)}"},
                       payload={"revoked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
