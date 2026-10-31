import os
import unittest
from unittest.mock import patch

from voice_telephony import validate_outbound_number, start_outbound_call


class VoiceTelephonyTests(unittest.TestCase):
    def test_requires_e164_number_in_allowlist(self):
        self.assertEqual(
            validate_outbound_number("+996555123456", ["+996555123456"]),
            "+996555123456",
        )

    def test_rejects_number_not_in_allowlist(self):
        with self.assertRaises(ValueError):
            validate_outbound_number("+996555123456", ["+996700000000"])

    def test_call_requires_explicit_confirmation(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(PermissionError):
                import asyncio
                asyncio.run(start_outbound_call("+996555123456", confirm_call=False))

    def test_paid_ai_and_outbound_call_guards_default_to_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(PermissionError):
                import asyncio
                asyncio.run(start_outbound_call("+996555123456", confirm_call=True))

    def test_missing_agent_configuration_blocks_call(self):
        with patch.dict(os.environ, {
            "MCP_ALLOW_PAID_AI": "true",
            "MCP_ALLOW_OUTBOUND_CALLS": "true",
            "VOICE_CALL_ALLOWED_NUMBERS": "+996555123456",
        }, clear=True):
            with self.assertRaises(RuntimeError):
                import asyncio
                asyncio.run(start_outbound_call("+996555123456", confirm_call=True))

    def test_rejects_invalid_number_format(self):
        for value in ("0555123456", "+996 555 123456", "+00012345678", "+123"):
            with self.assertRaises(ValueError):
                validate_outbound_number(value, [value])


if __name__ == "__main__":
    unittest.main()
