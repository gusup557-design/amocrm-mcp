import ast
import os
import pathlib
import types
import unittest
from unittest.mock import patch


SERVER = pathlib.Path(__file__).resolve().parents[1] / "server.py"


class _FakeToolRegistry:
    def __init__(self, count):
        self.tools = [object() for _ in range(count)]

    async def list_tools(self):
        return self.tools


class _FakeDatabase:
    async def __call__(self, *args, **kwargs):
        return []


class _FakeJsonResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code


class HealthStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_returns_the_live_registered_tool_count(self):
        source = SERVER.read_text(encoding="utf-8")
        module = ast.parse(source)
        health_function = next(
            node
            for node in module.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "health_check"
        )
        namespace = {
            "Request": object,
            "JSONResponse": _FakeJsonResponse,
            "httpx": types.SimpleNamespace(HTTPError=Exception),
            "os": os,
            "db": _FakeDatabase(),
            "mcp": _FakeToolRegistry(3),
        }
        isolated = ast.Module(body=[health_function], type_ignores=[])
        exec(compile(isolated, str(SERVER), "exec"), namespace)

        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "",
                "SUPABASE_SECRET_KEY": "",
                "SUPABASE_SERVICE_ROLE_KEY": "",
            },
        ):
            response = await namespace["health_check"](object())

        self.assertEqual(response.payload["status"], "ok")
        self.assertEqual(response.payload["tools"], 3)

    async def test_health_reports_zero_when_the_tool_registry_is_empty(self):
        source = SERVER.read_text(encoding="utf-8")
        module = ast.parse(source)
        health_function = next(
            node
            for node in module.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "health_check"
        )
        namespace = {
            "Request": object,
            "JSONResponse": _FakeJsonResponse,
            "httpx": types.SimpleNamespace(HTTPError=Exception),
            "os": os,
            "db": _FakeDatabase(),
            "mcp": _FakeToolRegistry(0),
        }
        isolated = ast.Module(body=[health_function], type_ignores=[])
        exec(compile(isolated, str(SERVER), "exec"), namespace)

        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "",
                "SUPABASE_SECRET_KEY": "",
                "SUPABASE_SERVICE_ROLE_KEY": "",
            },
        ):
            response = await namespace["health_check"](object())

        self.assertEqual(response.payload["tools"], 0)


if __name__ == "__main__":
    unittest.main()
