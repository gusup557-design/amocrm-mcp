"""Request-scoped MCP session identity for safe account selection.

The MCP Streamable HTTP transport supplies the session identifier in the
mcp-session-id request header. ContextVar keeps concurrent requests isolated.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Awaitable, Callable


MCP_SESSION_ID_HEADER = b"mcp-session-id"
_CURRENT_MCP_SESSION_ID: ContextVar[str | None] = ContextVar(
    "current_mcp_session_id",
    default=None,
)


def get_current_mcp_session_id() -> str | None:
    """Return the Streamable HTTP session ID for the current request, if present."""
    return _CURRENT_MCP_SESSION_ID.get()


class McpSessionScopeMiddleware:
    """Expose each HTTP request's MCP session ID through a request-local ContextVar."""

    def __init__(self, app: Callable[..., Awaitable[Any]]) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        raw_session_id = headers.get(MCP_SESSION_ID_HEADER)
        session_id: str | None = None
        if raw_session_id:
            try:
                decoded = raw_session_id.decode("ascii")
            except UnicodeDecodeError:
                decoded = ""
            if decoded and len(decoded) <= 256:
                session_id = decoded

        context_token = _CURRENT_MCP_SESSION_ID.set(session_id)
        try:
            await self.app(scope, receive, send)
        finally:
            _CURRENT_MCP_SESSION_ID.reset(context_token)
