import ast
import pathlib
import unittest

from crm_mutations import validate_entity_update_payload, validate_task_update_payload


class EntityUpdateValidationTests(unittest.TestCase):
    def test_contact_update_accepts_documented_fields(self):
        payload = {
            "first_name": "Иван",
            "last_name": "Иванов",
            "responsible_user_id": 42,
            "custom_fields_values": [
                {"field_code": "PHONE", "values": [{"value": "+996700000000", "enum_code": "WORK"}]}
            ],
            "tags_to_add": [{"name": "VIP"}],
            "tags_to_delete": [{"id": 12}],
        }
        self.assertEqual(validate_entity_update_payload("contacts", payload), payload)

    def test_company_update_accepts_documented_fields(self):
        payload = {"name": "ОсОО Пример", "responsible_user_id": 42, "tags_to_add": [{"id": 12}]}
        self.assertEqual(validate_entity_update_payload("companies", payload), payload)

    def test_entity_update_rejects_unknown_entities_and_readonly_keys(self):
        for entity, payload in (
            ("leads", {"name": "X"}),
            ("contacts", {"id": 1, "name": "X"}),
            ("companies", {"account_id": 1, "name": "X"}),
            ("contacts", {"_links": {}}),
            ("companies", {}),
        ):
            with self.subTest(entity=entity, payload=payload):
                with self.assertRaises(ValueError):
                    validate_entity_update_payload(entity, payload)

    def test_tags_require_exactly_one_valid_id_or_name(self):
        for tag in ({}, {"id": 0}, {"id": 1, "name": "VIP"}, {"name": " "}):
            with self.subTest(tag=tag):
                with self.assertRaises(ValueError):
                    validate_entity_update_payload("contacts", {"tags_to_add": [tag]})

    def test_responsible_user_id_must_be_positive_integer(self):
        for value in (0, -1, True, "42"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_entity_update_payload("contacts", {"responsible_user_id": value})


class TaskUpdateValidationTests(unittest.TestCase):
    def test_accepts_task_reschedule_and_completion_payloads(self):
        self.assertEqual(
            validate_task_update_payload({"text": "Позвонить", "complete_till": 1793470000}),
            {"text": "Позвонить", "complete_till": 1793470000},
        )
        self.assertEqual(
            validate_task_update_payload({"is_completed": True, "result": {"text": "Готово"}}),
            {"is_completed": True, "result": {"text": "Готово"}},
        )

    def test_rejects_task_system_fields_and_bad_values(self):
        for payload in (
            {},
            {"id": 1, "text": "x"},
            {"account_id": 1},
            {"is_completed": "yes"},
            {"complete_till": True},
            {"result": {"text": ""}},
            {"entity_type": "unknown"},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    validate_task_update_payload(payload)

    def test_task_tool_contract(self):
        path = pathlib.Path(__file__).resolve().parents[1] / "server.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        functions = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        expected = {"get_task", "update_task", "update_contact", "update_company"}
        self.assertTrue(expected.issubset(functions))
        for name in ("update_task", "update_contact", "update_company"):
            body = ast.get_source_segment(source, functions[name])
            self.assertIn("confirm_write", body)


if __name__ == "__main__":
    unittest.main()
