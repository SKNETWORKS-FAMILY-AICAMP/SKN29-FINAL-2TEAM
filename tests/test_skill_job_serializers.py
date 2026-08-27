from datetime import datetime, timezone
from unittest import TestCase
from django.test import override_settings

from apps.skills.serializers import job_response


class SkillJobResponseTests(TestCase):
    def setUp(self):
        self.job = {
            "job_id": "job-1",
            "skill_name": "translate-ko-en-ja",
            "operation": "CREATE",
            "status": "FAILED",
            "stage": "TESTING",
            "failure_code": "TRIGGER_ACCURACY_TOO_LOW",
            "failure_summary": "internal metrics",
            "failure_details": {"precision": 0.5},
            "progress_message": "여러 요청에서 스킬이 알맞게 선택되는지 반복 확인하고 있어요.",
            "progress_current": 18,
            "progress_total": 36,
            "progress_events": [
                {
                    "message": "검증에 사용할 상황을 준비했어요.",
                    "at": "2026-08-26T00:00:00+00:00",
                    "current": None,
                    "total": None,
                },
                {
                    "message": "여러 요청에서 스킬이 알맞게 선택되는지 반복 확인하고 있어요.",
                    "at": "2026-08-26T00:01:00+00:00",
                    "current": 18,
                    "total": 36,
                },
            ],
            "candidate_document": {
                "name": "translate-ko-en-ja",
                "description": "한국어를 영어와 일본어로 번역할 때 사용합니다.",
                "body": "번역 절차",
            },
            "created_at": datetime(2026, 8, 26, tzinfo=timezone.utc),
        }

    def test_list_response_does_not_include_candidate_body(self):
        self.assertNotIn("candidate_document", job_response(self.job))

    def test_detail_response_includes_candidate_for_repair(self):
        response = job_response(self.job, include_candidate=True)
        self.assertEqual(response["candidate_document"], self.job["candidate_document"])

    def test_progress_exposes_current_activity_and_count(self):
        response = job_response(self.job)
        self.assertEqual(response["progress_current"], 18)
        self.assertEqual(response["progress_total"], 36)
        self.assertEqual(len(response["progress_events"]), 2)

    def test_old_row_without_progress_gets_stage_default(self):
        old = {key: value for key, value in self.job.items() if not key.startswith("progress_")}
        response = job_response(old)
        self.assertIn("반복해서 확인", response["progress_message"])
        self.assertEqual(response["progress_events"], [])

    @override_settings(SKILL_VALIDATION_QUEUE_DELAY_SECONDS=1)
    def test_오래_기다린_queue는_자연어_대기_이유를_준다(self):
        queued = {**self.job, "status": "QUEUED", "stage": "WAITING"}
        response = job_response(queued, worker_available=True)
        self.assertTrue(response["queue_delayed"])
        self.assertIn("앞선 검증", response["waiting_reason"])

    def test_워커가_없으면_서버_연결_대기를_알린다(self):
        queued = {**self.job, "status": "QUEUED", "stage": "WAITING"}
        response = job_response(queued, worker_available=False)
        self.assertIn("서버가 연결", response["waiting_reason"])
