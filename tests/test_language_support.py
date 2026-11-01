import unittest

from language_support import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    get_language_profile,
    normalize_language,
    resolve_language,
)


class LanguageSupportTests(unittest.TestCase):
    def test_supported_languages_cover_initial_cis_release(self):
        self.assertEqual(
            set(SUPPORTED_LANGUAGES),
            {"ru-RU", "ky-KG", "kk-KZ", "uz-UZ"},
        )

    def test_normalizes_language_codes_and_aliases(self):
        self.assertEqual(normalize_language("ru"), "ru-RU")
        self.assertEqual(normalize_language("kg"), "ky-KG")
        self.assertEqual(normalize_language("ky"), "ky-KG")
        self.assertEqual(normalize_language("kk"), "kk-KZ")
        self.assertEqual(normalize_language("uz"), "uz-UZ")
        self.assertEqual(normalize_language("UZ-uz"), "uz-UZ")

    def test_unknown_or_empty_language_is_not_silently_misclassified(self):
        self.assertIsNone(normalize_language("az"))
        self.assertIsNone(normalize_language(""))
        self.assertIsNone(normalize_language(None))

    def test_resolution_prefers_contact_preference_over_detection(self):
        self.assertEqual(
            resolve_language(preferred_language="ky", detected_language="ru"),
            "ky-KG",
        )

    def test_resolution_uses_detection_then_fallback(self):
        self.assertEqual(
            resolve_language(detected_language="kk-KZ"),
            "kk-KZ",
        )
        self.assertEqual(
            resolve_language(detected_language="az", fallback_language="uz"),
            "uz-UZ",
        )

    def test_resolution_defaults_to_russian(self):
        self.assertEqual(resolve_language(), DEFAULT_LANGUAGE)

    def test_profile_is_safe_and_contains_native_label(self):
        profile = get_language_profile("ky")
        self.assertEqual(profile["locale"], "ky-KG")
        self.assertEqual(profile["native_name"], "Кыргызча")
        self.assertTrue(profile["enabled"])


if __name__ == "__main__":
    unittest.main()
