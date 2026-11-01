import unittest

from crm_write_guard import require_explicit_confirmation


class CRMWriteGuardTests(unittest.TestCase):
    def test_only_literal_true_authorizes_a_write(self):
        for value in (False, None, 1, "true"):
            with self.subTest(value=value):
                with self.assertRaises(PermissionError):
                    require_explicit_confirmation(value, "confirm_write")

    def test_confirmed_write_is_allowed_by_per_call_guard(self):
        self.assertIsNone(require_explicit_confirmation(True, "confirm_write"))


if __name__ == "__main__":
    unittest.main()
