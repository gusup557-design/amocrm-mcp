import os
import unittest
from unittest.mock import patch

from voice_telephony import validate_outbound_number, start_outbound_call, build_outbound_call_payload


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

    def test_passes_crm_contact_and_language_as_dynamic_variables(self):
        payload = build_outbound_call_payload(
            agent_id="agent-1",
            phone_number_id="phone-1",
            to_number="+996555123456",
            crm_contact_id=123,
            preferred_language="ky",
        )
        self.assertEqual(
            payload["conversation_initiation_client_data"]["dynamic_variables"],
            {"crm_contact_id": "123", "preferred_language": "ky-KG"},
        )

    def test_omits_client_data_when_no_contact_or_language_was_supplied(self):
        payload = build_outbound_call_payload(
            agent_id="agent-1",
            phone_number_id="phone-1",
            to_number="+996555123456",
        )
        self.assertNotIn("conversation_initiation_client_data", payload)

    def test_rejects_invalid_contact_id(self):
        with self.assertRaises(ValueError):
            build_outbound_call_payload(
                agent_id="agent-1",
                phone_number_id="phone-1",
                to_number="+996555123456",
                crm_contact_id=-1,
            )

    def test_rejects_invalid_number_format(self):
        for value in ("0555123456", "+996 555 123456", "+00012345678", "+123"):
            with self.assertRaises(ValueError):
                validate_outbound_number(value, [value])


if __name__ == "__main__":
    unittest.main()
