import unittest

from transcription import (
    get_scribe_language_code,
    validate_audio_source_url,
)


class TranscriptionProviderTests(unittest.TestCase):
    def test_maps_all_four_locales_to_scribe_language_codes(self):
        self.assertEqual(get_scribe_language_code("ru"), "rus")
        self.assertEqual(get_scribe_language_code("ky-KG"), "kir")
        self.assertEqual(get_scribe_language_code("kk"), "kaz")
        self.assertEqual(get_scribe_language_code("uz-UZ"), "uzb")

    def test_unknown_language_is_rejected(self):
        with self.assertRaises(ValueError):
            get_scribe_language_code("az")

    def test_source_url_requires_https_and_allowlisted_host(self):
        self.assertEqual(
            validate_audio_source_url(
                "https://storage.example.com/call.mp3",
                ["example.com"],
            ),
            "https://storage.example.com/call.mp3",
        )
        with self.assertRaises(ValueError):
            validate_audio_source_url("http://storage.example.com/call.mp3", ["example.com"])
        with self.assertRaises(ValueError):
            validate_audio_source_url("https://evil.example.net/call.mp3", ["example.com"])

    def test_source_url_rejects_credentials_and_fragments(self):
        with self.assertRaises(ValueError):
            validate_audio_source_url(
                "https://user:pass@storage.example.com/call.mp3",
                ["example.com"],
            )
        with self.assertRaises(ValueError):
            validate_audio_source_url(
                "https://storage.example.com/call.mp3#fragment",
                ["example.com"],
            )


if __name__ == "__main__":
    unittest.main()
