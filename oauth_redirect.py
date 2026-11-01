"""Helpers for constructing OAuth authorization redirects."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def build_authorization_redirect_url(redirect_uri, code: str, state: str) -> str:
    """Return redirect_uri with exactly one authorization code and state."""
    parsed = urlsplit(str(redirect_uri))
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in {"code", "state"}
    ]
    query_items.extend((("code", code), ("state", state)))
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query_items), parsed.fragment)
    )
