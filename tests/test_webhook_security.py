import hashlib
import hmac
import unittest

from webhook_security import (
    verify_amocrm_chat_signature,
    verify_elevenlabs_signature,
)


class WebhookSecurityTests(unittest.TestCase):
    def test_accepts_valid_amocrm_chat_signature_over_trimmed_raw_body(self):
        body = b'  {"event_type":"new_message"}\n'
        signature = hmac.new(
            b"chat-secret",
            body.strip(),
            hashlib.sha1,
        ).hexdigest()
        self.assertTrue(
            verify_amocrm_chat_signature(body, signature, "chat-secret")
        )

    def test_rejects_invalid_or_missing_amocrm_signature(self):
        self.assertFalse(
            verify_amocrm_chat_signature(b"{}", "invalid", "chat-secret")
        )
        self.assertFalse(
            verify_amocrm_chat_signature(b"{}", "", "chat-secret")
        )
        self.assertFalse(
            verify_amocrm_chat_signature(b"{}", "00" * 20, "")
        )

    def test_accepts_valid_elevenlabs_signature_and_preserves_raw_body(self):
        timestamp = "1793450000"
        body = b'{ "type": "post_call_transcription" }\n'
        signed = timestamp.encode("ascii") + b"." + body
        digest = hmac.new(
            b"webhook-secret",
            signed,
            hashlib.sha256,
        ).hexdigest()
        header = f"t={timestamp},v0={digest}"
        self.assertTrue(
            verify_elevenlabs_signature(
                body,
                header,
                "webhook-secret",
                now=1793450000,
            )
        )

    def test_rejects_changed_body_or_wrong_secret(self):
        timestamp = "1793450000"
        body = b'{"type":"post_call_transcription"}'
        signed = timestamp.encode("ascii") + b"." + body
        digest = hmac.new(b"webhook-secret", signed, hashlib.sha256).hexdigest()
        header = f"t={timestamp},v0={digest}"
        self.assertFalse(
            verify_elevenlabs_signature(
                body + b" ",
                header,
                "webhook-secret",
                now=1793450000,
            )
        )
        self.assertFalse(
            verify_elevenlabs_signature(
                body,
                header,
                "wrong-secret",
                now=1793450000,
            )
        )

    def test_uses_documented_thirty_minute_timestamp_tolerance_by_default(self):
        timestamp = "1793449000"
        body = b"{}"
        digest = hmac.new(
            b"webhook-secret",
            timestamp.encode("ascii") + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        self.assertTrue(
            verify_elevenlabs_signature(
                body,
                f"t={timestamp},v0={digest}",
                "webhook-secret",
                now=1793450000,
            )
        )

    def test_rejects_old_or_future_elevenlabs_timestamps(self):
        timestamp = "1793440000"
        body = b"{}"
        digest = hmac.new(
            b"webhook-secret",
            timestamp.encode("ascii") + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        header = f"t={timestamp},v0={digest}"
        self.assertFalse(
            verify_elevenlabs_signature(
                body,
                header,
                "webhook-secret",
                now=1793450000,
                tolerance_seconds=60,
            )
        )
        future = "1793451000"
        future_digest = hmac.new(
            b"webhook-secret",
            future.encode("ascii") + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        self.assertFalse(
            verify_elevenlabs_signature(
                body,
                f"t={future},v0={future_digest}",
                "webhook-secret",
                now=1793450000,
                tolerance_seconds=60,
            )
        )

    def test_rejects_malformed_duplicate_and_missing_signature_parts(self):
        for header in (
            "",
            "v0=abcd",
            "t=abc,v0=" + "0" * 64,
            "t=1793450000,t=1793450001,v0=" + "0" * 64,
            "t=1793450000,v0=" + "0" * 64 + ",v0=" + "1" * 64,
            "t=1793450000,v0=not-hex",
        ):
            self.assertFalse(
                verify_elevenlabs_signature(
                    b"{}",
                    header,
                    "webhook-secret",
                    now=1793450000,
                ),
                msg=header,
            )


if __name__ == "__main__":
    unittest.main()
