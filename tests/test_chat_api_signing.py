import unittest

from chat_api import build_chat_headers, verify_chat_webhook_signature


class ChatApiSigningTests(unittest.TestCase):
    def test_headers_match_amocrm_hmac_sha1_contract(self):
        headers = build_chat_headers(
            method="POST",
            path="/v2/origin/custom/channel-id/connect",
            body=b'{"account_id":"123"}',
            secret="test-channel-secret",
            date_header="Sat, 31 Oct 2026 12:00:00 +0000",
        )
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Content-MD5"], "f28ac64419aed3b15e9cd5bee8e3f6cc")
        self.assertEqual(headers["X-Signature"], "504683e870bb317e5dceecb771a1752390c2c3d9")
        self.assertEqual(len(headers["X-Signature"]), 40)
        self.assertEqual(headers["X-Signature"], headers["X-Signature"].lower())

    def test_get_signs_empty_body_and_exact_path_without_query(self):
        headers = build_chat_headers(
            method="GET",
            path="/v2/origin/custom/scope/chats/conversation/history",
            body=b"",
            secret="secret",
            date_header="Sat, 31 Oct 2026 12:00:00 +0000",
        )
        self.assertEqual(headers["Content-MD5"], "d41d8cd98f00b204e9800998ecf8427e")

    def test_verifies_webhook_signature_from_raw_body(self):
        body = b'{"event_type":"new_message"}'
        self.assertTrue(
            verify_chat_webhook_signature(
                body,
                "channel-secret",
                "1808242be3be3a54577fa234f0f2bf2544f924fe",
            )
        )

    def test_rejects_invalid_webhook_signature(self):
        self.assertFalse(
            verify_chat_webhook_signature(
                b'{"event_type":"new_message"}',
                "channel-secret",
                "invalid",
            )
        )

    def test_rejects_query_string_in_signed_path(self):
        with self.assertRaises(ValueError):
            build_chat_headers("GET", "/history?limit=50", b"", "secret")

    def test_rejects_missing_secret_and_invalid_method(self):
        with self.assertRaises(ValueError):
            build_chat_headers("GET", "/history", b"", "")
        with self.assertRaises(ValueError):
            build_chat_headers("PUT", "/history", b"", "secret")


if __name__ == "__main__":
    unittest.main()
