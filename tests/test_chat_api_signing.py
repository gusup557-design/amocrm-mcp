import unittest

from chat_api import build_chat_headers


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
        self.assertEqual(headers["Content-MD5"], "f2a6b3f2b8c5b73a0f7b2b0f4c3a9a7d")
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
