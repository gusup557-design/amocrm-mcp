import ast
import pathlib
import unittest

SERVER = pathlib.Path(__file__).resolve().parents[1] / "server.py"


class LanguageMcpToolContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SERVER.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.tools = {
            node.name
            for node in ast.walk(cls.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "mcp"
                and decorator.func.attr == "tool"
                for decorator in node.decorator_list
            )
        }

    def test_language_tools_are_exposed_over_mcp(self):
        self.assertTrue(
            {"get_supported_languages", "resolve_conversation_language", "chat_get_history", "chat_send_text_message", "transcription_transcribe_audio_url", "voice_start_outbound_call", "conversation_preview_post_call_actions"}.issubset(self.tools)
        )

    def test_original_tools_are_preserved_and_total_count_is_updated(self):
        self.assertEqual(len(self.tools), 49)

    def test_language_module_is_imported_by_server(self):
        self.assertIn("from language_support import", self.source)


if __name__ == "__main__":
    unittest.main()
