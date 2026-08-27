"""`backend.db.skill_jobs` — raw SQL 계층의 손으로 만든 커서 mock 테스트.

`test_evaluation_db.py`와 같은 패턴이다 — `database_connection()`을 가짜로
바꿔 실제 Postgres 없이 SQL 문장과 인자만 확인한다. 나머지 메서드
(claim_next의 FOR UPDATE SKIP LOCKED, heartbeat, mark_succeeded/failed 등)는
실제 컨테이너에서 직접 검증했다("얇은 종단 경로" 작업기록) — 여기서는
2026-08-26에 실제로 버그였던 지점(QUEUED 취소가 영원히 CANCEL_REQUESTED에
머무는 문제)과 "열린 job은 하나" 순서(멱등키 → 열린 job 조회 → INSERT)만
고정한다.
"""

from __future__ import annotations

import unittest
from contextlib import contextmanager
from unittest.mock import patch

from backend.db import skill_jobs
from backend.db.skill_jobs import STATUS_CANCELED, STATUS_CANCEL_REQUESTED, SkillRegistrationJobRepository


class _Cursor:
    def __init__(self, fetchone_results):
        self._fetchone_results = iter(fetchone_results)
        self.executed: list[tuple[str, tuple]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=()):
        self.executed.append((sql, params))

    def fetchone(self):
        return next(self._fetchone_results, None)


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def rollback(self):
        pass


def _connection_factory(cursor):
    @contextmanager
    def factory():
        yield _Connection(cursor)

    return factory


class RequestCancelTests(unittest.TestCase):
    """2026-08-26 실제로 겪은 버그 — QUEUED job을 취소하면 `CANCEL_REQUESTED`로만
    표시했는데, `claim_next()`는 `QUEUED`/만료된 `RUNNING`만 집어서 그 job을
    다시 건드릴 워커가 없었다(취소도 삭제도 안 되는 상태로 영원히 남음).
    `CASE WHEN` 하나로 고쳤다 — QUEUED는 그 자리에서 바로 CANCELED로 끝낸다."""

    def test_queued_job_cancels_immediately_not_cancel_requested(self):
        cursor = _Cursor([{"status": STATUS_CANCELED, "job_id": "j1"}])
        with patch.object(skill_jobs, "database_connection", _connection_factory(cursor)):
            row = SkillRegistrationJobRepository.request_cancel("j1", account_id="AC001")

        self.assertEqual(row["status"], STATUS_CANCELED)
        sql, params = cursor.executed[0]
        # CASE WHEN이 QUEUED -> CANCELED, 그 외(RUNNING) -> CANCEL_REQUESTED로
        # 분기한다는 것을 SQL 문자열 자체로 고정한다 — 다시 예전처럼 단일 값
        # UPDATE로 되돌아가면 이 assert가 깨진다.
        self.assertIn("CASE WHEN status = %s THEN %s ELSE %s END", sql)
        self.assertEqual(params[:3], (skill_jobs.STATUS_QUEUED, STATUS_CANCELED, STATUS_CANCEL_REQUESTED))

    def test_no_matching_open_job_raises_not_found(self):
        cursor = _Cursor([None])
        with patch.object(skill_jobs, "database_connection", _connection_factory(cursor)):
            with self.assertRaises(skill_jobs.SkillJobNotFound):
                SkillRegistrationJobRepository.request_cancel("missing", account_id="AC001")


class ClaimNextTests(unittest.TestCase):
    def test_same_account_jobs_are_serialized_while_other_accounts_can_run(self):
        cursor = _Cursor([None])
        with patch.object(skill_jobs, "database_connection", _connection_factory(cursor)):
            result = SkillRegistrationJobRepository.claim_next(lease_owner="worker-1", lease_seconds=120)

        self.assertIsNone(result)
        sql, params = cursor.executed[0]
        self.assertIn("running.account_id = candidate.account_id", sql)
        self.assertIn("running.job_id <> candidate.job_id", sql)
        self.assertIn("running.lease_expires_at >= now()", sql)
        self.assertEqual(params[-1], skill_jobs.STATUS_RUNNING)


class DeleteTerminalTests(unittest.TestCase):
    def test_only_deletes_failed_or_canceled(self):
        class _DeleteCursor(_Cursor):
            rowcount = 1

        cursor = _DeleteCursor([])
        with patch.object(skill_jobs, "database_connection", _connection_factory(cursor)):
            SkillRegistrationJobRepository.delete_terminal("j1", account_id="AC001")

        _sql, params = cursor.executed[0]
        self.assertEqual(params[2], [skill_jobs.STATUS_FAILED, STATUS_CANCELED])

    def test_nothing_deleted_raises_not_found(self):
        class _DeleteCursor(_Cursor):
            rowcount = 0

        cursor = _DeleteCursor([])
        with patch.object(skill_jobs, "database_connection", _connection_factory(cursor)):
            with self.assertRaises(skill_jobs.SkillJobNotFound):
                SkillRegistrationJobRepository.delete_terminal("j1", account_id="AC001")


class UpdateProgressTests(unittest.TestCase):
    def test_progress_records_message_count_and_event(self):
        class _UpdateCursor(_Cursor):
            rowcount = 1

        cursor = _UpdateCursor([])
        with patch.object(skill_jobs, "database_connection", _connection_factory(cursor)):
            SkillRegistrationJobRepository.update_progress(
                "j1",
                lease_owner="worker-1",
                message="반복 확인 중",
                current=12,
                total=36,
            )

        sql, params = cursor.executed[0]
        self.assertIn("progress_message", sql)
        self.assertEqual(params[0:3], ("반복 확인 중", 12, 36))
        self.assertEqual(params[-3:], ("j1", "worker-1", skill_jobs.STATUS_RUNNING))
