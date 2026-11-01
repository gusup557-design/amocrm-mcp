import ast
import pathlib
import unittest

from pipeline_statuses import (
    ensure_pipeline_status_is_editable,
    validate_pipeline_status_payload,
)


class PipelineStatusValidationTests(unittest.TestCase):
    def test_create_requires_name_and_sort(self):
        valid = {"name": "Новый этап", "sort": 60}
        self.assertEqual(validate_pipeline_status_payload(valid, "create"), valid)
        for payload in ({"name": "x"}, {"sort": 5}, {"name": "", "sort": 2}, {"name": "x", "sort": True}):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    validate_pipeline_status_payload(payload, "create")

    def test_update_requires_a_supported_change(self):
        for payload in ({}, {"type": 0}, {"id": 123}, {"is_editable": True}):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    validate_pipeline_status_payload(payload, "update")
        self.assertEqual(
            validate_pipeline_status_payload({"name": "Контакт", "color": "#c1e0ff"}, "update"),
            {"name": "Контакт", "color": "#c1e0ff"},
        )

    def test_color_must_be_from_documented_palette(self):
        self.assertEqual(
            validate_pipeline_status_payload({"name": "Этап", "sort": 10, "color": "#c1e0ff"}, "create")["color"],
            "#c1e0ff",
        )
        for color in ("red", "#123", "#123456", "javascript:alert(1)"):
            with self.subTest(color=color):
                with self.assertRaises(ValueError):
                    validate_pipeline_status_payload({"name": "Этап", "sort": 10, "color": color}, "create")

    def test_descriptions_have_unique_allowed_levels_and_length_limit(self):
        valid = {
            "name": "Этап",
            "sort": 10,
            "descriptions": [
                {"level": "newbie", "description": "Описание"},
                {"level": "candidate", "description": "Для кандидата"},
            ],
        }
        self.assertEqual(validate_pipeline_status_payload(valid, "create"), valid)
        invalid_sets = (
            [{"level": "newbie", "description": "A"}, {"level": "newbie", "description": "B"}],
            [{"level": "admin", "description": "A"}],
            [{"level": "master", "description": "x" * 1001}],
            [{"level": "candidate"}],
        )
        for descriptions in invalid_sets:
            with self.subTest(descriptions=descriptions):
                with self.assertRaises(ValueError):
                    validate_pipeline_status_payload(
                        {"name": "Этап", "sort": 10, "descriptions": descriptions},
                        "create",
                    )

    def test_description_deletion_requires_id_and_level_without_text(self):
        payload = {
            "name": "Этап",
            "descriptions": [{"id": 10, "level": "newbie"}],
        }
        self.assertEqual(validate_pipeline_status_payload(payload, "update"), payload)
        for description in (
            {"id": 0, "level": "newbie"},
            {"id": 10},
            {"level": "newbie", "description": "x" * 1001},
        ):
            with self.subTest(description=description):
                with self.assertRaises(ValueError):
                    validate_pipeline_status_payload(
                        {"descriptions": [description]},
                        "update",
                    )

    def test_status_must_belong_to_pipeline_and_be_editable(self):
        ensure_pipeline_status_is_editable(
            {"id": 12, "pipeline_id": 34, "is_editable": True},
            expected_pipeline_id=34,
            expected_status_id=12,
        )
        for status in (
            {"id": 142, "pipeline_id": 34, "is_editable": False},
            {"id": 12, "pipeline_id": 99, "is_editable": True},
            {"id": 13, "pipeline_id": 34, "is_editable": True},
            {"id": 12, "pipeline_id": 34},
        ):
            with self.subTest(status=status):
                with self.assertRaises(PermissionError):
                    ensure_pipeline_status_is_editable(status, 34, 12)


class PipelineStatusToolContractTests(unittest.TestCase):
    def test_pipeline_status_tools_exist_and_require_confirmations(self):
        path = pathlib.Path(__file__).resolve().parents[1] / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        functions = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        expected = {
            "get_pipeline_statuses",
            "get_pipeline_status",
            "create_pipeline_status",
            "update_pipeline_status",
            "delete_pipeline_status",
        }
        self.assertTrue(expected.issubset(functions))
        for name in ("create_pipeline_status", "update_pipeline_status", "delete_pipeline_status"):
            with self.subTest(name=name):
                body = ast.get_source_segment(source, functions[name])
                self.assertIn("confirm_", body)
        delete_body = ast.get_source_segment(source, functions["delete_pipeline_status"])
        self.assertIn("confirm_deal_reassignment", delete_body)


if __name__ == "__main__":
    unittest.main()
