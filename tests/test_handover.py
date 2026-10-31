import unittest

from handover import HANDOVER_CHECKS, build_client_handover_checklist


class ClientHandoverTests(unittest.TestCase):
    def test_empty_handover_is_not_ready(self):
        report = build_client_handover_checklist([])
        self.assertEqual(report["status"], "incomplete")
        self.assertFalse(report["ready_for_handover"])
        self.assertEqual(report["missing_count"], len(HANDOVER_CHECKS))

    def test_all_required_checks_mark_handover_ready(self):
        report = build_client_handover_checklist(list(HANDOVER_CHECKS))
        self.assertEqual(report["status"], "ready_for_handover")
        self.assertTrue(report["ready_for_handover"])
        self.assertEqual(report["missing_count"], 0)

    def test_missing_required_checks_are_listed(self):
        report = build_client_handover_checklist([
            "customer_admin_access",
            "client_owned_provider_accounts",
            "mcp_local_credentials_disconnected",
        ])
        self.assertFalse(report["ready_for_handover"])
        self.assertIn("billing_confirmed", report["missing_checks"])

    def test_unknown_check_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown handover check"):
            build_client_handover_checklist(["everything_is_done"])

    def test_duplicates_do_not_inflate_completion_count(self):
        report = build_client_handover_checklist([
            "customer_admin_access",
            "customer_admin_access",
        ])
        self.assertEqual(report["completed_count"], 1)

    def test_report_discloses_operator_attestation_limit(self):
        report = build_client_handover_checklist([])
        self.assertTrue(report["operator_attestation_only"])
        self.assertIn("not independently verified", report["verification_limit"])


if __name__ == "__main__":
    unittest.main()
