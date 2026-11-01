import unittest

from oauth_redirect import build_authorization_redirect_url


class AnyUrlLike:
    """Minimal URL value object matching Pydantic AnyUrl's string contract."""

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return self.value


class OAuthRedirectTests(unittest.TestCase):
    def test_url_object_redirect_adds_authorization_code_and_state(self):
        redirect_uri = AnyUrlLike("https://client.example/callback")
        actual = build_authorization_redirect_url(redirect_uri, "auth-code", "csrf-state")
        self.assertEqual(
            actual,
            "https://client.example/callback?code=auth-code&state=csrf-state",
        )

    def test_existing_query_and_fragment_are_preserved(self):
        redirect_uri = AnyUrlLike("https://client.example/callback?tenant=west#finish")
        actual = build_authorization_redirect_url(redirect_uri, "auth-code", "csrf-state")
        self.assertEqual(
            actual,
            "https://client.example/callback?tenant=west&code=auth-code&state=csrf-state#finish",
        )

    def test_existing_oauth_parameters_are_replaced_not_duplicated(self):
        redirect_uri = AnyUrlLike(
            "https://client.example/callback?code=old&state=old-state&mode=login"
        )
        actual = build_authorization_redirect_url(redirect_uri, "new-code", "new-state")
        self.assertEqual(
            actual,
            "https://client.example/callback?mode=login&code=new-code&state=new-state",
        )


if __name__ == "__main__":
    unittest.main()
