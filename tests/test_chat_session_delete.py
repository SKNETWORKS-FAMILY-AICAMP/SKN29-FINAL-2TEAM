"""대화 삭제가 **대화 본문을 전부** 지우는지 지킨다.

새 엔진은 LangGraph 체크포인트에 대화 상태를 담고 `thread_id` 로 `session_id` 를
쓴다. `chat_message` 만 지우면 `checkpoint_blobs` 에 메시지·도구 호출·승인 대기가
그대로 남는다 — 사용자는 지웠다고 생각하는데 DB 에는 있는 상태다.

2026-08-19 실측: 실제 RDS 에 주인 없는 체크포인트가 282행(대화 7개분) 쌓여
있었다. 이 테스트가 없어서 아무도 못 봤다.
"""

from unittest.mock import patch

from django.test import SimpleTestCase

from backend.db import agent_platform

SESSION_ID = "11111111-1111-1111-1111-111111111111"


class _Cursor:
    def __init__(self):
        self.statements: list[str] = []

    def execute(self, sql, params=None):
        self.statements.append(" ".join(str(sql).split()))

    def fetchone(self):
        # `_require_session` 이 소유 확인으로 부른다.
        return {"session_id": SESSION_ID, "account_id": "UA001", "team_id": "TE001"}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _connection(cursor):
    class _Conn:
        def cursor(self):
            return cursor

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    return lambda: _Conn()


def _deleting(cursor):
    return patch.object(agent_platform, "database_connection", _connection(cursor))


class SessionDeleteTests(SimpleTestCase):
    def _run(self) -> _Cursor:
        cursor = _Cursor()
        with _deleting(cursor):
            agent_platform.ChatSessionRepository.delete(
                session_id=SESSION_ID, account_id="UA001"
            )
        return cursor

    def _index_of(self, cursor: _Cursor, needle: str) -> int:
        for index, sql in enumerate(cursor.statements):
            if needle in sql:
                return index
        self.fail(f"이 문장을 안 돌렸다: {needle}")

    def test_체크포인트_세_종류를_모두_지운다(self):
        cursor = self._run()

        for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
            self.assertTrue(
                any(f"DELETE FROM {table} " in sql for sql in cursor.statements),
                f"{table} 를 안 지우면 대화 본문이 DB 에 남는다",
            )

    def test_대화_행보다_먼저_지운다(self):
        """순서가 곧 정확성이다 — `chat_session` 을 먼저 지우면 thread_id 를 찾을
        방법이 없어져 완전 삭제로도 못 지우는 고아가 된다."""

        cursor = self._run()
        session_row = self._index_of(cursor, "DELETE FROM chat_session")

        for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
            self.assertLess(
                self._index_of(cursor, f"DELETE FROM {table} "),
                session_row,
                f"{table} 는 chat_session 보다 먼저 지워야 한다",
            )

    def test_실행_기록은_남긴다(self):
        """`agent_run`·`tool_call` 은 평가의 모수라 사용자의 정리로 줄면 안 된다."""

        cursor = self._run()
        joined = " ".join(cursor.statements)

        self.assertNotIn("DELETE FROM agent_run", joined)
        self.assertNotIn("DELETE FROM tool_call", joined)

    def test_소유_확인이_지우기보다_먼저다(self):
        """`_require_session` 이 팀을 확인한 **뒤에** 첫 DELETE 가 나가야 한다.
        순서가 뒤집히면 남의 대화를 지운 뒤에 거절하게 된다."""

        cursor = self._run()
        first_delete = next(
            index for index, sql in enumerate(cursor.statements) if sql.startswith("DELETE")
        )
        checked = next(
            index
            for index, sql in enumerate(cursor.statements)
            if "FROM chat_session" in sql and not sql.startswith("DELETE")
        )

        self.assertLess(checked, first_delete)
