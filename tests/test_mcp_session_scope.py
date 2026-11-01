import asyncio
import unittest

from mcp_session_scope import (
    MCP_SESSION_ID_HEADER,
    McpSessionScopeMiddleware,
    get_current_mcp_session_id,
)


class SessionScopeMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_reads_session_id_from_streamable_http_header(self):
        observed = []

        async def app(scope, receive, send):
            observed.append(get_current_mcp_session_id())

        middleware = McpSessionScopeMiddleware(app)
        await middleware(
            {
                "type": "http",
                "headers": [(MCP_SESSION_ID_HEADER, b"session-one")],
            },
            None,
            None,
        )
        self.assertEqual(observed, ["session-one"])
        self.assertIsNone(get_current_mcp_session_id())

    async def test_missing_session_header_is_not_replaced_with_global_state(self):
        observed = []

        async def app(scope, receive, send):
            observed.append(get_current_mcp_session_id())

        middleware = McpSessionScopeMiddleware(app)
        await middleware({"type": "http", "headers": []}, None, None)
        self.assertEqual(observed, [None])

    async def test_concurrent_requests_keep_separate_session_ids(self):
        observed = asyncio.Queue()

        async def app(scope, receive, send):
            await asyncio.sleep(0)
            await observed.put(get_current_mcp_session_id())

        middleware = McpSessionScopeMiddleware(app)

        async def invoke(session_id):
            await middleware(
                {
                    "type": "http",
                    "headers": [(MCP_SESSION_ID_HEADER, session_id.encode("ascii"))],
                },
                None,
                None,
            )

        await asyncio.gather(invoke("session-alpha"), invoke("session-beta"))
        results = {await observed.get(), await observed.get()}
        self.assertEqual(results, {"session-alpha", "session-beta"})


if __name__ == "__main__":
    unittest.main()
