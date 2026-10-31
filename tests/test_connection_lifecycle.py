import ast
import pathlib
import unittest

from connection_lifecycle import (
    ensure_disconnect_confirmation,
    ensure_no_other_active_account,
    public_connection_summaries,
    select_single_active_connection,
)


class ConnectionSelectionTests(unittest.TestCase):
    def test_requires_an_existing_connection(self):
        with self.assertRaisesRegex(RuntimeError, "not connected"):
            select_single_active_connection([])

    def test_selects_the_only_connected_account(self):
        row = {"account_id": 42, "base_domain": "acme.amocrm.ru"}
        self.assertIs(select_single_active_connection([row]), row)

    def test_refuses_to_choose_arbitrarily_between_accounts(self):
        rows = [
            {"account_id": 42, "base_domain": "one.amocrm.ru"},
            {"account_id": 84, "base_domain": "two.amocrm.ru"},
        ]
        with self.assertRaisesRegex(RuntimeError, "more than one"):
            select_single_active_connection(rows)

    def test_refuses_a_second_distinct_account_until_disconnect(self):
        with self.assertRaisesRegex(PermissionError, "disconnect"):
            ensure_no_other_active_account(
                [{"account_id": 42, "base_domain": "one.amocrm.ru"}],
                requested_account_id=84,
            )

    def test_allows_reauthorizing_the_same_account(self):
        ensure_no_other_active_account(
            [{"account_id": 42, "base_domain": "one.amocrm.ru"}],
            requested_account_id=42,
        )

    def test_disconnect_requires_explicit_confirmation(self):
        with self.assertRaises(PermissionError):
            ensure_disconnect_confirmation(False)
        ensure_disconnect_confirmation(True)

    def test_public_connection_summary_never_returns_secrets(self):
        rows = [{
            "account_id": 42,
            "base_domain": "acme.amocrm.ru",
            "expires_at": "2026-10-31T18:00:00Z",
            "access_token_enc": "ACCESS-SECRET",
            "refresh_token_enc": "REFRESH-SECRET",
            "client_secret_enc": "CLIENT-SECRET",
        }]
        result = public_connection_summaries(rows)
        self.assertEqual(result[0]["account_id"], 42)
        serialized = repr(result)
        for secret in ("ACCESS-SECRET", "REFRESH-SECRET", "CLIENT-SECRET"):
            self.assertNotIn(secret, serialized)


    def test_legacy_static_amo_credentials_are_not_used(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        server_source = (root / "server.py").read_text(encoding="utf-8")
        env_example = (root / ".env.example").read_text(encoding="utf-8")
        self.assertNotIn('os.environ.get("AMOCRM_TOKEN"', server_source)
        self.assertNotIn('os.environ.get("AMOCRM_DOMAIN"', server_source)
        self.assertNotIn("AMOCRM_TOKEN=", env_example)
        self.assertNotIn("AMOCRM_DOMAIN=", env_example)


class ConnectionToolContractTests(unittest.TestCase):
    def test_connection_management_tools_are_exposed(self):
        server_path = pathlib.Path(__file__).resolve().parents[1] / "server.py"
        tree = ast.parse(server_path.read_text(encoding="utf-8"))
        tool_names = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and isinstance(decorator.func.value, ast.Name)
                    and decorator.func.value.id == "mcp"
                    and decorator.func.attr == "tool"
                ):
                    tool_names.add(node.name)
        self.assertTrue(
            {"list_amocrm_connections", "disconnect_amocrm_connection"}.issubset(tool_names)
        )


if __name__ == "__main__":
    unittest.main()
