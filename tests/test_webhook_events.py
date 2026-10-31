import unittest

from webhook_events import build_webhook_event_identity


class WebhookEventIdentityTests(unittest.TestCase):
    def test_chat_message_uses_provider_message_id(self):
        payload = {
            "event_type": "new_message",
            "payload": {"msgid": "msg-123", "conversation_id": "conv-1"},
        }
        self.assertEqual(
            build_webhook_event_identity("amocrm_chat", payload, b"raw"),
            ("amocrm_chat", "new_message", "msg-123", "conv-1"),
        )

    def test_elevenlabs_uses_conversation_and_event_timestamp(self):
        payload = {
            "type": "post_call_transcription",
            "event_timestamp": 1739537297,
            "data": {"conversation_id": "conv-abc"},
        }
        self.assertEqual(
            build_webhook_event_identity("elevenlabs", payload, b"raw"),
            (
                "elevenlabs",
                "post_call_transcription",
                "post_call_transcription:conv-abc:1739537297",
                "conv-abc",
            ),
        )

    def test_distinguishes_event_types_for_the_same_conversation_timestamp(self):
        transcript = {"type": "post_call_transcription", "event_timestamp": 7, "data": {"conversation_id": "c"}}
        failure = {"type": "call_initiation_failure", "event_timestamp": 7, "data": {"conversation_id": "c"}}
        transcript_id = build_webhook_event_identity("elevenlabs", transcript, b"one")[2]
        failure_id = build_webhook_event_identity("elevenlabs", failure, b"two")[2]
        self.assertNotEqual(transcript_id, failure_id)

    def test_unknown_or_incomplete_events_use_body_digest_fallback(self):
        payload = {"type": "custom_event", "data": {}}
        result = build_webhook_event_identity("elevenlabs", payload, b"same-body")
        self.assertEqual(result[0], "elevenlabs")
        self.assertEqual(result[1], "custom_event")
        import hashlib
        self.assertEqual(result[2], hashlib.sha256(b"same-body").hexdigest())
        self.assertIsNone(result[3])

    def test_rejects_unknown_provider_and_invalid_payload(self):
        with self.assertRaises(ValueError):
            build_webhook_event_identity("other", {}, b"{}")
        with self.assertRaises(ValueError):
            build_webhook_event_identity("elevenlabs", [], b"{}")


if __name__ == "__main__":
    unittest.main()
