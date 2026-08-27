from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings


class SkillCleanupCommandTests(SimpleTestCase):
    @override_settings(
        SKILL_VALIDATION_SUCCEEDED_RETENTION_DAYS=31,
        SKILL_VALIDATION_TERMINAL_RETENTION_DAYS=32,
        SKILL_EVAL_FEEDBACK_RETENTION_DAYS=91,
        SKILL_EVAL_UNAPPROVED_CASE_RETENTION_DAYS=92,
    )
    @patch("apps.skills.management.commands.cleanup_skill_validation_jobs.SkillEvalFeedbackRepository.cleanup_expired")
    @patch("apps.skills.management.commands.cleanup_skill_validation_jobs.SkillRegistrationJobRepository.cleanup_expired")
    def test_검증_기록과_회귀_데이터를_각각_보존_정책으로_정리한다(self, cleanup_jobs, cleanup_eval):
        cleanup_jobs.return_value = {"redacted": 2, "deleted": 3}
        cleanup_eval.return_value = {"feedback_deleted": 4, "case_deleted": 5}
        output = StringIO()

        call_command("cleanup_skill_validation_jobs", "--dry-run", stdout=output)

        cleanup_jobs.assert_called_once_with(succeeded_days=31, terminal_days=32, dry_run=True)
        cleanup_eval.assert_called_once_with(feedback_days=91, unapproved_case_days=92, dry_run=True)
        self.assertIn("신고 삭제 4건", output.getvalue())
        self.assertIn("미승인 회귀 사례 삭제 5건", output.getvalue())
