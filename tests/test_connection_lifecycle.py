import pathlib
import unittest

from connection_lifecycle import (
    ensure_disconnect_confirmation,
    public_connection_summaries,
    resolve_connection_for_session,
)


class ConnectionSelectionTests(unittest.TestCase):
    def test_requires_an_existing_connection(self):
        with self.assertRaisesRegex(RuntimeError, "not connected"):
            resolve_connection_for_session([], None)

    def test_keeps_single_account_compatibility(self):
        row = {"account_id": 42, "base_domain": "one.amocrm.ru"}
        self.assertIs(resolve_connection_for_session([row], None), row)

    def test_requires_explicit_selection_when_multiple_accounts_are_connected(self):
        rows = [
            {"account_id": 42, "base_domain": "one.amocrm.ru"},
            {"account_id": 84, "base_domain": "two.amocrm.ru"},
        ]
        with self.assertRaisesRegex(RuntimeError, "select_amocrm_account"):
            resolve_connection_for_session(rows, None)

    def test_resolves_selected_account_without_switching_other_sessions(self):
        rows = [
            {"account_id": 42, "base_domain": "one.amocrm.ru"},
            {"account_id": 84, "base_domain": "two.amocrm.ru"},
        ]
        self.assertEqual(resolve_connection_for_session(rows, 84)["account_id"], 84)
        self.assertEqual(resolve_connection_for_session(rows, 42)["account_id"], 42)

    def test_rejects_a_stale_selection_after_manual_disconnect(self):
        rows = [{"account_id": 42, "base_domain": "one.amocrm.ru"}]
        with self.assertRaisesRegex(LookupError, "no longer connected"):
            resolve_connection_for_session(rows, 84)

    def test_expired_guarantee_date_does_not_expire_or_remove_connection(self):
        row = {
            "account_id": 42,
            "base_domain": "one.amocrm.ru",
            "guarantee_until": "2020-01-01T00:00:00Z",
        }
        self.assertIs(resolve_connection_for_session([row], None), row)

    def test_disconnect_requires_explicit_confirmation(self):
        with self.assertRaises(PermissionError):
            ensure_disconnect_confirmation(False)
        ensure_disconnect_confirmation(True)

    def test_public_connection_catalog_never_returns_secrets(self):
        rows = [
            {
                "account_id": 42,
                "account_name": "Customer One",
                "base_domain": "one.amocrm.ru",
                "created_at": "2026-11-01T00:00:00Z",
                "guarantee_until": "2026-11-08T00:00:00Z",
                "expires_at": "2026-11-01T01:00:00Z",
                "access_token_enc": "ACCESS-SECRET",
                "refresh_token_enc": "REFRESH-SECRET",
                "client_secret_enc": "CLIENT-SECRET",
            },
            {
                "account_id": 84,
                "account_name": "Customer Two",
                "base_domain": "two.amocrm.ru",
                "created_at": "2026-11-02T00:00:00Z",
                "guarantee_until": "2026-11-09T00:00:00Z",
                "expires_at": "2026-11-02T01:00:00Z",
            },
        ]
        result = public_connection_summaries(rows, selected_account_id=84)
        self.assertEqual(len(result), 2)
        self.assertFalse(result[0]["selected"])
        self.assertTrue(result[1]["selected"])
        self.assertEqual(result[0]["account_name"], "Customer One")
        self.assertEqual(result[0]["guarantee_until"], "2026-11-08T00:00:00Z")
        serialized = repr(result)
        for secret in ("ACCESS-SECRET", "REFRESH-SECRET", "CLIENT-SECRET"):
            self.assertNotIn(secret, serialized)


class ConnectionToolContractTests(unittest.TestCase):
    def test_connection_catalog_and_selection_tools_are_exposed(self):
        server_path = pathlib.Path(__file__).resolve().parents[1] / "server.py"
        source = server_path.read_text(encoding="utf-8")
        for name in (
            "list_amocrm_connections",
            "select_amocrm_account",
            "get_selected_amocrm_account",
            "disconnect_amocrm_connection",
        ):
            with self.subTest(tool=name):
                self.assertIn(f"async def {name}(", source)


if __name__ == "__main__":
    unittest.main()
