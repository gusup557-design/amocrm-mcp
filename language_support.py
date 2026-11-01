"""Language preferences and locale resolution for CIS customer conversations.

Language detection is intentionally provider-agnostic: STT/chat adapters supply a
detected locale, while this module applies the contact preference and fallback
policy consistently.
"""
from __future__ import annotations

from typing import Optional

DEFAULT_LANGUAGE = "ru-RU"

SUPPORTED_LANGUAGES = {
    "ru-RU": {
        "locale": "ru-RU",
        "short_code": "ru",
        "native_name": "Русский",
        "english_name": "Russian",
        "enabled": True,
    },
    "ky-KG": {
        "locale": "ky-KG",
        "short_code": "ky",
        "native_name": "Кыргызча",
        "english_name": "Kyrgyz",
        "enabled": True,
    },
    "kk-KZ": {
        "locale": "kk-KZ",
        "short_code": "kk",
        "native_name": "Қазақша",
        "english_name": "Kazakh",
        "enabled": True,
    },
    "uz-UZ": {
        "locale": "uz-UZ",
        "short_code": "uz",
        "native_name": "Oʻzbekcha",
        "english_name": "Uzbek",
        "enabled": True,
    },
}

_ALIASES = {
    "ru": "ru-RU",
    "ru-ru": "ru-RU",
    "russian": "ru-RU",
    "ky": "ky-KG",
    "ky-kg": "ky-KG",
    "kg": "ky-KG",
    "kg-kg": "ky-KG",
    "kyrgyz": "ky-KG",
    "kk": "kk-KZ",
    "kk-kz": "kk-KZ",
    "kz": "kk-KZ",
    "kz-kz": "kk-KZ",
    "kazakh": "kk-KZ",
    "uz": "uz-UZ",
    "uz-uz": "uz-UZ",
    "uzbek": "uz-UZ",
}


def normalize_language(language: Optional[str]) -> Optional[str]:
    """Return a supported BCP-47 locale, or None for unknown input."""
    if not isinstance(language, str):
        return None
    candidate = language.strip().replace("_", "-").lower()
    if not candidate:
        return None
    return _ALIASES.get(candidate)


def get_language_profile(language: Optional[str]) -> dict:
    """Return a copy of the public profile for a supported language."""
    locale = normalize_language(language)
    if locale is None:
        raise ValueError("Unsupported language; use ru, ky, kk, or uz")
    return dict(SUPPORTED_LANGUAGES[locale])


def resolve_language(
    preferred_language: Optional[str] = None,
    detected_language: Optional[str] = None,
    fallback_language: Optional[str] = None,
) -> str:
    """Resolve language by contact preference, detection, explicit fallback, default."""
    for candidate in (
        preferred_language,
        detected_language,
        fallback_language,
        DEFAULT_LANGUAGE,
    ):
        normalized = normalize_language(candidate)
        if normalized:
            return normalized
    return DEFAULT_LANGUAGE
