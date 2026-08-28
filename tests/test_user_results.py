import json

from django.test import SimpleTestCase

from services.agent_runtime.user_results import (
    USER_RESULT_ABSENCES_MAX,
    USER_RESULT_ITEMS_MAX,
    USER_RESULT_PEOPLE_MAX,
    build_user_result,
)


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
                "limitations": [
                    "공휴일 캘린더가 없어 월~금을 근무일로 계산했다.",
                    "회의·돌발업무는 반영하지 않았다(cal_event를 채우는 경로가 없다).",
                ],
                "credential": "never expose",
            },
            ensure_ascii=False,
        )

        result = build_user_result(tool_ref="workload_report", content=content)

        self.assertEqual(result["kind"], "workload_report")
        self.assertEqual(result["people_count"], 1)
        self.assertEqual(result["people"][0]["remaining_capacity"], 120)
        self.assertEqual(
            result["warnings"]["limitations"],
            [
                "공휴일 정보가 없어 월요일부터 금요일까지를 근무일로 계산했습니다.",
                "회의와 돌발 업무는 반영되지 않았습니다.",
            ],
        )
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("person_id", serialized)
        self.assertNotIn("project_key", serialized)
        self.assertNotIn("credential", serialized)
        self.assertNotIn("cal_event", serialized)

    def test_workload_result_is_bounded_but_reports_total(self):
        people = [{"name": f"팀원 {index}"} for index in range(USER_RESULT_PEOPLE_MAX + 3)]
        result = build_user_result(
            tool_ref="workload_report", content=json.dumps({"people": people}, ensure_ascii=False)
        )

        self.assertEqual(result["people_count"], USER_RESULT_PEOPLE_MAX + 3)
        self.assertEqual(len(result["people"]), USER_RESULT_PEOPLE_MAX)

    def test_absence_result_is_allowlisted_and_bounded(self):
        absences = [
            {
                "person_id": f"PB{index:03d}",
                "name": f"팀원 {index}",
                "absence_type": "ANNUAL",
                "start_at": "2026-09-01",
                "end_at": "2026-09-02",
                "private_note": "노출 금지",
            }
            for index in range(USER_RESULT_ABSENCES_MAX + 2)
        ]
        result = build_user_result(
            tool_ref="absence_list",
            content=json.dumps(
                {"period": {"start": "2026-08-27", "end": "2026-09-24"}, "absences": absences},
                ensure_ascii=False,
            ),
        )

        self.assertEqual(result["absence_count"], USER_RESULT_ABSENCES_MAX + 2)
        self.assertEqual(len(result["absences"]), USER_RESULT_ABSENCES_MAX)
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("person_id", serialized)
        self.assertNotIn("private_note", serialized)

    def test_jira_result_keeps_counts_and_bounded_user_fields(self):
        result = build_user_result(
            tool_ref="jira_get_issues",
            content=json.dumps(
                {
                    "project_key": "HALIL",
                    "total": 7,
                    "counts": {"TO_DO": 3, "IN_PROGRESS": 2, "DONE": 2, "UNKNOWN": 0},
                    "upcoming": [
                        {
                            "key": "HALIL-1",
                            "title": "로그인 회귀 확인",
                            "due": "2026-08-30",
                            "assignee_email": "secret@example.com",
                        }
                    ],
                    "credential_account_id": "UA001",
                },
                ensure_ascii=False,
            ),
        )

        self.assertEqual(result["total"], 7)
        self.assertEqual(result["counts"]["in_progress"], 2)
        self.assertEqual(result["upcoming"][0]["key"], "HALIL-1")
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("assignee_email", serialized)
        self.assertNotIn("credential_account_id", serialized)

    def test_datetime_result_omits_unlisted_fields(self):
        result = build_user_result(
            tool_ref="get_current_datetime",
            content=json.dumps(
                {
                    "date": "2026-08-27",
                    "time": "17:00:00",
                    "timezone": "Asia/Seoul",
                    "weekday": "Thursday",
                    "weekday_kr": "목",
                    "server_host": "private-host",
                }
            ),
        )

        self.assertEqual(result["kind"], "current_datetime")
        self.assertEqual(result["weekday_kr"], "목")
        self.assertNotIn("server_host", result)
        self.assertNotIn("weekday", result)

    def test_people_projects_and_tasks_are_allowlisted_and_bounded(self):
        fixtures = [
            (
                "people_list",
                "members",
                {"person_id": "PB001", "name": "윤수아", "job_role": "본부장", "org_name": "개발팀"},
                "member_count",
                "person_id",
            ),
            (
                "project_list",
                "projects",
                {"proj_id": "PJ001", "name": "한빛몰", "status": "ACTIVE", "progress": 42},
                "project_count",
                "proj_id",
            ),
            (
                "task_list",
                "tasks",
                {
                    "task_id": "TK001",
                    "title": "회귀 테스트",
                    "status": "CONFIRMED",
                    "priority": "HIGH",
                    "due_at": "2026-09-01",
                    "effort_hours": 4,
                    "required_role": "QA",
                },
                "task_count",
                "task_id",
            ),
        ]
        for tool_ref, key, row, count_key, private_key in fixtures:
            with self.subTest(tool_ref=tool_ref):
                result = build_user_result(
                    tool_ref=tool_ref,
                    content=json.dumps({key: [row] * (USER_RESULT_ITEMS_MAX + 1)}, ensure_ascii=False),
                )
                self.assertEqual(result[count_key], USER_RESULT_ITEMS_MAX + 1)
                self.assertEqual(len(result[key]), USER_RESULT_ITEMS_MAX)
                self.assertNotIn(private_key, json.dumps(result, ensure_ascii=False))

    def test_document_list_separates_collected_and_pending_without_ids_or_errors(self):
        result = build_user_result(
            tool_ref="document_list",
            content=json.dumps(
                {
                    "documents": [
                        {
                            "doc_id": "DC001",
                            "file_name": "기획서.pdf",
                            "project": "한빛몰",
                            "role": "이 프로젝트의 기준 문서",
                            "search_ready": False,
                        }
                    ],
                    "not_collected": [
                        {
                            "external_id": "drive-secret",
                            "file_name": "회의록.docx",
                            "folder": "팀 공유",
                            "supported": True,
                        }
                    ],
                    "truncated": True,
                    "storage_error": "oauth token expired: secret",
                },
                ensure_ascii=False,
            ),
        )

        self.assertEqual(result["document_count"], 1)
        self.assertEqual(result["not_collected_count"], 1)
        self.assertTrue(result["storage_unavailable"])
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("doc_id", serialized)
        self.assertNotIn("external_id", serialized)
        self.assertNotIn("oauth", serialized)

    def test_unknown_or_invalid_tool_output_has_no_user_result(self):
        self.assertIsNone(build_user_result(tool_ref="mcp:custom", content='{"secret":"x"}'))
        self.assertIsNone(build_user_result(tool_ref="workload_report", content="not-json"))
