import ast
import pathlib
import unittest

SERVER = pathlib.Path(__file__).resolve().parents[1] / "server.py"


class UpstreamToolPreservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SERVER.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

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
        self.assertEqual(expected, exposed)

    def test_tls_verification_is_enabled(self):
        self.assertNotIn("verify=False", self.source)
        self.assertIn("verify=True", self.source)

    def test_read_and_write_helpers_are_preserved(self):
        self.assertIn("async def api_get(", self.source)
        self.assertIn("async def api_post(", self.source)
        self.assertIn("async def api_patch(", self.source)

    def test_entity_note_paths_are_allowlisted(self):
        self.assertGreaterEqual(self.source.count('entity_type not in {"leads", "contacts", "companies"}'), 2)


if __name__ == "__main__":
    unittest.main()
