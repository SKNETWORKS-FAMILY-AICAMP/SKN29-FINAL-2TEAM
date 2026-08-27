import json

from django.test import SimpleTestCase

from services.agent_runtime.user_results import USER_RESULT_PEOPLE_MAX, build_user_result


class UserToolResultTests(SimpleTestCase):
    def test_workload_result_copies_only_user_fields(self):
        content = json.dumps(
            {
                "period_start": "2026-08-27",
                "period_end": "2026-09-24",
                "workdays": 20,
                "as_of": "2026-08-27T07:00:00+00:00",
                "workload_weeks": 4,
                "people": [
                    {
                        "person_id": "PB001",
                        "name": "김지훈 과장",
                        "job_role": "과장",
                        "effective_capacity": 160,
                        "current_allocation": 40,
                        "remaining_capacity": 120,
                        "load_rate": 25,
                        "blocked_reason": None,
                        "by_project": [{"project_key": "SECRET", "hours": 40}],
                    }
                ],
                "missing_estimate_count": 2,
                "unmapped_assignee_count": 1,
                "unscheduled_backlog_hours": 8,
                "limitations": ["공휴일 캘린더가 없습니다."],
                "credential": "never expose",
            },
            ensure_ascii=False,
        )

        result = build_user_result(tool_ref="workload_report", content=content)

        self.assertEqual(result["kind"], "workload_report")
        self.assertEqual(result["people_count"], 1)
        self.assertEqual(result["people"][0]["remaining_capacity"], 120)
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("person_id", serialized)
        self.assertNotIn("project_key", serialized)
        self.assertNotIn("credential", serialized)

    def test_workload_result_is_bounded_but_reports_total(self):
        people = [{"name": f"팀원 {index}"} for index in range(USER_RESULT_PEOPLE_MAX + 3)]
        result = build_user_result(
            tool_ref="workload_report", content=json.dumps({"people": people}, ensure_ascii=False)
        )

        self.assertEqual(result["people_count"], USER_RESULT_PEOPLE_MAX + 3)
        self.assertEqual(len(result["people"]), USER_RESULT_PEOPLE_MAX)

    def test_unknown_or_invalid_tool_output_has_no_user_result(self):
        self.assertIsNone(build_user_result(tool_ref="mcp:custom", content='{"secret":"x"}'))
        self.assertIsNone(build_user_result(tool_ref="workload_report", content="not-json"))
