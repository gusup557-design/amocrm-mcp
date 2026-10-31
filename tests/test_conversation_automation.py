import unittest

from conversation_automation import build_post_call_action_plan


class PostCallAutomationTests(unittest.TestCase):
    def test_builds_note_and_followup_plan_for_correlated_contact(self):
        payload = {
            "type": "post_call_transcription",
            "data": {
                "conversation_id": "conv-1",
                "status": "done",
                "analysis": {
                    "transcript_summary": "Customer asked for a quote.",
                    "call_successful": "success",
                },
                "conversation_initiation_client_data": {
                    "dynamic_variables": {
                        "crm_contact_id": "123",
                        "preferred_language": "ky",
                    }
                },
            },
        }
        plan = build_post_call_action_plan(payload)
        self.assertEqual(plan["contact_id"], 123)
        self.assertEqual(plan["language"], "ky-KG")
        self.assertEqual([x["type"] for x in plan["proposed_actions"]], ["add_note", "create_follow_up_task"])

    def test_does_not_propose_crm_writes_without_a_valid_contact_id(self):
        payload = {
            "type": "post_call_transcription",
            "data": {
                "conversation_id": "conv-2",
                "status": "done",
                "analysis": {"transcript_summary": "Call summary"},
                "conversation_initiation_client_data": {"dynamic_variables": {}},
            },
        }
        plan = build_post_call_action_plan(payload)
        self.assertIsNone(plan["contact_id"])
        self.assertEqual(plan["proposed_actions"], [])
        self.assertEqual(plan["requires"], "contact_match")

    def test_ignores_incomplete_or_unsupported_call_events(self):
        payload = {"type": "call_initiation_failure", "data": {"conversation_id": "conv-3"}}
        plan = build_post_call_action_plan(payload)
        self.assertEqual(plan["proposed_actions"], [])
        self.assertEqual(plan["status"], "not_actionable")

    def test_rejects_non_object_payload(self):
        with self.assertRaises(ValueError):
            build_post_call_action_plan([])


if __name__ == "__main__":
    unittest.main()
