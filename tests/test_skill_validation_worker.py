"""장시간 평가 중 검증 job lease 유지 회귀 테스트."""

import time
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.skills.management.commands.skill_validation_worker import Command


class WorkerHeartbeatTests(SimpleTestCase):
    @patch("apps.skills.management.commands.skill_validation_worker.run_publishing")
    @patch("apps.skills.management.commands.skill_validation_worker.run_testing")
    @patch("apps.skills.management.commands.skill_validation_worker.run_preparing_tests")
    @patch("apps.skills.management.commands.skill_validation_worker.run_checking")
    @patch("apps.skills.management.commands.skill_validation_worker.SkillRegistrationJobRepository")
    def test_실행중_취소는_다음_progress에서_CANCELED로_닫는다(
        self, repository, _checking, preparing, _testing, _publishing
    ):
        job = {
            "job_id": "job-cancel",
            "skill_name": "cancel-skill",
            "operation": "CREATE",
            "lease_owner": "worker-1",
        }
        repository.is_cancel_requested.return_value = False
        repository.get.return_value = job

        def _cancel_during_preparing(_job, *, progress):
            repository.is_cancel_requested.return_value = True
            progress("검토 중", 1, 3)

        preparing.side_effect = _cancel_during_preparing
        Command()._process(job, lease_owner="worker-1", lease_seconds=120)

        repository.mark_canceled.assert_called_once_with(
            "job-cancel", lease_owner="worker-1"
        )
        repository.mark_succeeded.assert_not_called()

    @patch("apps.skills.management.commands.skill_validation_worker.run_publishing")
    @patch("apps.skills.management.commands.skill_validation_worker.run_testing")
    @patch("apps.skills.management.commands.skill_validation_worker.run_preparing_tests")
    @patch("apps.skills.management.commands.skill_validation_worker.run_checking")
    @patch("apps.skills.management.commands.skill_validation_worker.SkillRegistrationJobRepository")
    def test_단계가_오래_걸려도_별도_heartbeat가_lease를_연장한다(
        self, repository, run_checking, run_preparing, run_testing, run_publishing
    ):
        del run_checking, run_testing, run_publishing
        job = {
            "job_id": "job-1",
            "skill_name": "sample-skill",
            "operation": "CREATE",
            "lease_owner": "worker-1",
        }
        repository.is_cancel_requested.return_value = False
        repository.get.return_value = job
        def _slow_preparing(_job, *, progress):
            progress("테스트 상황을 만들고 있어요.", 1, 3)
            time.sleep(0.08)

        run_preparing.side_effect = _slow_preparing

        with patch(
            "apps.skills.management.commands.skill_validation_worker.HEARTBEAT_INTERVAL_SECONDS",
            0.01,
        ):
            Command()._process(job, lease_owner="worker-1", lease_seconds=1)

        self.assertGreaterEqual(repository.heartbeat.call_count, 1)
        progress_messages = [call.kwargs["message"] for call in repository.update_progress.call_args_list]
        self.assertIn("테스트 상황을 만들고 있어요.", progress_messages)
        self.assertIn("검증을 통과한 내용을 개인 스킬로 저장하고 있어요.", progress_messages)
        repository.mark_succeeded.assert_called_once_with("job-1", lease_owner="worker-1")
