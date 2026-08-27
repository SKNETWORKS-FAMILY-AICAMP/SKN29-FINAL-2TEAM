from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.accounts.tokens import issue_token
from backend.db.skill_jobs import SkillJobNotFound

from .test_accounts import member_profile


def _auth(account_id="UA001"):
    return {"authorization": f"Bearer {issue_token(account_id)}"}


def _job(**overrides):
    row = {
        "job_id": "11111111-1111-1111-1111-111111111111",
        "skill_name": "sample-skill", "operation": "CREATE", "attempt": 1,
        "retry_of_job_id": None, "status": "FAILED", "stage": "TESTING",
        "failure_code": "EVAL_JOB_TIMEOUT", "failure_summary": "시간 초과",
        "failure_details": {}, "progress_events": [],
        "candidate_document": {"name": "sample-skill", "description": "설명", "body": "절차"},
    }
    row.update(overrides)
    return row


class SkillJobApiTests(SimpleTestCase):
    def test_all_job_routes_require_login(self):
        urls = [
            "/api/skill-registration-jobs/",
            "/api/skill-registration-jobs/job-1/",
            "/api/skill-registration-jobs/job-1/cancel/",
            "/api/skill-registration-jobs/job-1/retry/",
        ]
        methods = [self.client.get, self.client.get, self.client.post, self.client.post]
        for method, url in zip(methods, urls, strict=True):
            self.assertEqual(method(url).status_code, 401)

    @patch("backend.db.skill_operations.SkillWorkerHeartbeatRepository.active_count", return_value=1)
    @patch("apps.skills.api_views.SkillRegistrationJobRepository.list_for_account")
    def test_list_is_scoped_to_authenticated_account(self, list_for_account, _heartbeat):
        list_for_account.return_value = [_job()]
        response = self.client.get(
            "/api/skill-registration-jobs/?open=true", headers=_auth("UA001")
        )
        self.assertEqual(response.status_code, 200)
        list_for_account.assert_called_once_with("UA001", open_only=True)
        self.assertNotIn("candidate_document", response.json()[0])

    @patch("backend.db.skill_operations.SkillWorkerHeartbeatRepository.active_count", return_value=1)
    @patch("apps.skills.api_views.SkillRegistrationJobRepository.get")
    def test_detail_returns_candidate_only_after_ownership_check(self, get, _heartbeat):
        get.return_value = _job()
        response = self.client.get(
            "/api/skill-registration-jobs/job-1/", headers=_auth("UA001")
        )
        self.assertEqual(response.status_code, 200)
        get.assert_called_once_with("job-1", account_id="UA001")
        self.assertEqual(response.json()["candidate_document"]["name"], "sample-skill")

    @patch("apps.skills.api_views.SkillRegistrationJobRepository.request_cancel")
    def test_cancel_is_scoped_and_returns_terminal_state(self, cancel):
        cancel.return_value = _job(status="CANCELED", stage="WAITING", failure_code=None)
        response = self.client.post(
            "/api/skill-registration-jobs/job-1/cancel/", headers=_auth("UA001")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "CANCELED")
        cancel.assert_called_once_with("job-1", account_id="UA001")

    @patch(
        "apps.skills.api_views.SkillRegistrationJobRepository.delete_terminal",
        side_effect=SkillJobNotFound("삭제할 수 없습니다."),
    )
    def test_delete_rejects_missing_or_nonterminal_job(self, _delete):
        response = self.client.delete(
            "/api/skill-registration-jobs/job-1/", headers=_auth("UA001")
        )
        self.assertEqual(response.status_code, 404)

    @patch("apps.skills.api_views.SkillRegistrationService.retry")
    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_retry_uses_authenticated_account_and_current_team(self, get_profile, retry):
        profile = member_profile()
        profile["team_id"] = "TM001"
        get_profile.return_value = profile
        retry.return_value = SimpleNamespace(job=_job(status="QUEUED", stage="WAITING", failure_code=None), created=True)
        response = self.client.post(
            "/api/skill-registration-jobs/job-1/retry/",
            {"candidate_document": {"name": "sample-skill", "description": "새 설명", "body": "새 절차"}},
            content_type="application/json", headers=_auth("UA001"),
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(retry.call_args.kwargs["account_id"], "UA001")
        self.assertEqual(retry.call_args.kwargs["team_id"], "TM001")
