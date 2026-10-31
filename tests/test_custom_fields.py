import ast
import pathlib
import unittest

from custom_fields import (
    ensure_custom_field_is_deletable,
    normalize_custom_field_entity,
    validate_custom_field_payload,
)


class CustomFieldPayloadTests(unittest.TestCase):
    def test_normalizes_only_supported_crm_entities(self):
        self.assertEqual(normalize_custom_field_entity("leads"), "leads")
        self.assertEqual(normalize_custom_field_entity("contacts"), "contacts")
        self.assertEqual(normalize_custom_field_entity("companies"), "companies")
        for value in ("customers", "catalogs", "../leads", "", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    normalize_custom_field_entity(value)

    def test_create_requires_name_and_type(self):
        self.assertEqual(
            validate_custom_field_payload({"name": "Бюджет", "type": "numeric"}, "create"),
            {"name": "Бюджет", "type": "numeric"},
        )
        for payload in ({"name": "Бюджет"}, {"type": "numeric"}, {"name": " ", "type": "numeric"}):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    validate_custom_field_payload(payload, "create")

    def test_enum_field_requires_nonempty_enum_values(self):
        valid = {
            "name": "Тип клиента",
            "type": "select",
            "enums": [{"value": "Частный", "sort": 1}, {"value": "Компания", "sort": 2}],
        }
        self.assertEqual(validate_custom_field_payload(valid, "create"), valid)
        for enums in (None, [], [{}], [{"value": " " , "sort": 1}], [{"value": "A"}]):
            with self.subTest(enums=enums):
                payload = {**valid, "enums": enums}
                with self.assertRaises(ValueError):
                    validate_custom_field_payload(payload, "create")

    def test_rejects_invalid_enum_item_types_and_sort_values(self):
        base = {"name": "Тип", "type": "select"}
        for enums in ("not-a-list", [None], [{"value": 1, "sort": 1}], [{"value": "x", "sort": True}]):
            with self.subTest(enums=enums):
                with self.assertRaises(ValueError):
                    validate_custom_field_payload({**base, "enums": enums}, "create")

    def test_update_requires_a_name_and_at_least_one_change(self):
        for payload in ({}, {"name": ""}, {"name": "   "}):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    validate_custom_field_payload(payload, "update")
        self.assertEqual(
            validate_custom_field_payload({"name": "Новый бюджет", "sort": 30}, "update"),
            {"name": "Новый бюджет", "sort": 30},
        )

    def test_rejects_read_only_properties_and_unknown_keys(self):
        for key in ("id", "account_id", "is_deletable", "entity_type", "_links", "unknown"):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    validate_custom_field_payload(
                        {"name": "Поле", "type": "text", key: 1},
                        "create" if key not in {"id", "account_id", "is_deletable", "entity_type", "_links"} else "update",
                    )

    def test_required_statuses_have_pipeline_and_status_ids(self):
        payload = {
            "name": "Источник",
            "type": "text",
            "required_statuses": [{"pipeline_id": 12, "status_id": 34}],
        }
        self.assertEqual(validate_custom_field_payload(payload, "create"), payload)
        invalid = {**payload, "required_statuses": [{"pipeline_id": 12}]}
        with self.assertRaises(ValueError):
            validate_custom_field_payload(invalid, "create")

    def test_delete_requires_explicitly_deletable_field(self):
        ensure_custom_field_is_deletable({"id": 3, "is_deletable": True}, 3)
        for field in (
            {"id": 3, "is_deletable": False},
            {"id": 3},
            {"id": 4, "is_deletable": True},
        ):
            with self.subTest(field=field):
                with self.assertRaises(PermissionError):
                    ensure_custom_field_is_deletable(field, 3)


class CustomFieldToolContractTests(unittest.TestCase):
    def test_create_update_delete_tools_are_guarded(self):
        path = pathlib.Path(__file__).resolve().parents[1] / "server.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        functions = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        expected = {"create_custom_field", "update_custom_field", "delete_custom_field"}
        self.assertTrue(expected.issubset(functions))
        for name in expected:
            with self.subTest(name=name):
                source = ast.get_source_segment(path.read_text(encoding="utf-8"), functions[name])
                self.assertIn("confirm_", source)


if __name__ == "__main__":
    unittest.main()
