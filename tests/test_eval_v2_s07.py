import unittest
from datetime import date

from scripts.eval_v2_s07 import _approval_fields, _is_expected_jira_request, _payload_fidelity


class EvalV2S07ScriptTests(unittest.TestCase):
    def test_non_jira_approval_does_not_satisfy_jira_contract(self):
        fields = _approval_fields([
            {"name": "task_register", "args": {"tasks": [{"title": "관측성"}]}}
        ])

        self.assertEqual(fields["action_names"], ["task_register"])
        self.assertFalse(_is_expected_jira_request(fields))

    def test_exact_single_jira_request_satisfies_jira_contract(self):
        fields = _approval_fields([{
            "name": "jira_create_issues",
            "args": {"issues": [{"title": "관측성", "issuetype": "Task"}]},
        }])

        self.assertTrue(_is_expected_jira_request(fields))

    def test_payload_fidelity_normalizes_yaml_date(self):
        fields = {
            "request_count": 1, "issue_count": 1,
            "title": "관측성 완료 기준 확정",
            "description": "발주사 운영팀과 수행사가 M1에서 주요 경로 5종을 정한다.",
            "duedate": "2026-10-30",
        }
        gold = {"approval_payload_gold": {
            "summary": "관측성 완료 기준 확정", "due_date": date(2026, 10, 30)
        }}

        self.assertTrue(_payload_fidelity(fields, gold))


if __name__ == "__main__":
    unittest.main()
