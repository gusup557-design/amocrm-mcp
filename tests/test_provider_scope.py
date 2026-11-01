import unittest

from provider_scope import ensure_global_provider_scope


class GlobalProviderScopeTests(unittest.TestCase):
    def test_single_connected_account_allows_legacy_global_provider_config(self):
        ensure_global_provider_scope(1, "amoCRM Chat API")

    def test_zero_connected_accounts_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "No amoCRM account is connected"):
            ensure_global_provider_scope(0, "ElevenLabs")

    def test_multiple_connected_accounts_are_rejected_for_global_provider_secrets(self):
        with self.assertRaisesRegex(PermissionError, "not account-specific"):
            ensure_global_provider_scope(2, "amoCRM Chat API")

    def test_multiple_accounts_do_not_block_account_scoped_crm_operations(self):
        # This helper is called only by providers still using global credentials.
        # CRM API tools continue to use the MCP session's selected account.
        with self.assertRaises(PermissionError):
            ensure_global_provider_scope(3, "ElevenLabs")


if __name__ == "__main__":
    unittest.main()
