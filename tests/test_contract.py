import ast
import pathlib
import unittest

SERVER = pathlib.Path(__file__).resolve().parents[1] / "server.py"
OAUTH_BACKEND = pathlib.Path(__file__).resolve().parents[1] / "oauth_backend.py"


class UpstreamToolPreservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SERVER.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.oauth_source = OAUTH_BACKEND.read_text(encoding="utf-8")
        ast.parse(cls.oauth_source)

    def test_all_upstream_tools_are_preserved(self):
        exposed = set()
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if any(
                    isinstance(d, ast.Call)
                    and isinstance(d.func, ast.Attribute)
                    and isinstance(d.func.value, ast.Name)
                    and d.func.value.id == "mcp"
                    and d.func.attr == "tool"
                    for d in node.decorator_list
                ):
                    exposed.add(node.name)
        expected = {
            "get_account_info", "get_leads", "get_lead", "create_lead",
            "update_lead", "get_contacts", "get_contact", "create_contact",
            "get_companies", "get_company", "create_company", "get_tasks",
            "create_task", "get_pipelines", "get_users", "add_note", "get_notes",
        }
        self.assertTrue(expected.issubset(exposed), f'Missing upstream tools: {sorted(expected - exposed)}')

    def test_tls_verification_is_enabled(self):
        self.assertNotIn("verify=False", self.source)
        self.assertIn("verify=True", self.source)

    def test_read_and_write_helpers_are_preserved(self):
        self.assertIn("async def api_get(", self.source)
        self.assertIn("async def api_post(", self.source)
        self.assertIn("async def api_patch(", self.source)

    def test_vercel_exposes_streamable_http_app(self):
        self.assertIn("app = mcp.streamable_http_app(", self.source)
        self.assertIn("TransportSecuritySettings", self.source)

    def test_supabase_health_probe_uses_existing_connections_table(self):
        self.assertIn("amocrm_connections?select=account_id", self.source)
        self.assertIn("SUPABASE_SERVICE_ROLE_KEY", self.source)

    def test_oauth_tokens_are_bound_to_mcp_resource(self):
        self.assertIn("validate_token_resource=True", self.source)
        self.assertIn("expected_resource", self.oauth_source)
        self.assertIn("resource=p.get(\"resource\")", self.oauth_source)

    def test_entity_note_paths_are_allowlisted(self):
        self.assertGreaterEqual(self.source.count('entity_type not in {"leads", "contacts", "companies"}'), 2)


if __name__ == "__main__":
    unittest.main()
