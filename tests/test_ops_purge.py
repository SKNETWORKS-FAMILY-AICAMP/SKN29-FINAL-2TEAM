"""완전 삭제(운영자 콘솔)의 **가드**를 확인한다.

지우는 SQL 자체보다 **안 지워야 할 때 안 지우는지**가 이 기능의 값이다.
되돌릴 수 없어서 한 번 잘못 지우면 확인할 방법이 없다.

`database_connection` 을 가짜로 바꿔 SQL 을 실제로 돌리지 않는다 — 이 저장소는
ORM 이 없어 테스트 DB 가 없고(`DATABASES = {}`), 진짜 RDS 를 지울 수는 없다.
"""

from unittest.mock import patch

from django.test import SimpleTestCase

from backend.db import repositories
from backend.db.errors import PermissionDenied, RecordNotFound


class _Cursor:
    """`purge_*` 가 부르는 조회만 흉내낸다. DELETE/UPDATE 는 세기만 한다."""

    def __init__(self, *, team=None, account=None, owned_teams=(), admin_count=1, team_owner="UA999"):
        self.team = team
        self.account = account
        self.owned_teams = list(owned_teams)
        self.admin_count = admin_count
        self.team_owner = team_owner
        self.executed = []
        self._last = ""
        self.rowcount = 0

    def execute(self, sql, params=None):
        self._last = sql
        self.executed.append(sql)
        self.rowcount = 0

    def fetchone(self):
        s = self._last
        if "FROM team WHERE team_id" in s and "owner_account_id" in s:
            return {"owner_account_id": self.team_owner}
        if "FROM team WHERE team_id" in s:
            return self.team
        if "FROM user_account WHERE account_id" in s:
            return self.account
        if "count(*) AS n FROM user_account WHERE is_admin" in s:
            return {"n": self.admin_count}
        if "count(*) AS n" in s:
            return {"n": 0}
        return None

    def fetchall(self):
        if "FROM team WHERE owner_account_id" in self._last:
            return self.owned_teams
        return []

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

    def _factory():
        return _Conn()

    return _factory


def _purging(cursor):
    return patch.object(repositories, "database_connection", _connection(cursor))


class TeamPurgeGuardTests(SimpleTestCase):
    def test_이름이_다르면_지우지_않는다(self):
        cursor = _Cursor(team={"team_id": "TE002", "name": "개발팀B"})
        with _purging(cursor), self.assertRaises(PermissionDenied):
            repositories.OpsPurgeRepository.purge_team(
                team_id="TE002", actor_account_id="UA001", confirm_name="개발팀"
            )
        self.assertNotIn(
            "DELETE FROM team WHERE team_id = %(team_id)s",
            cursor.executed,
            "확인이 틀렸는데 지우기 시작하면 안 된다",
        )

    def test_본인이_속한_팀은_못_지운다(self):
        cursor = _Cursor(team={"team_id": "TE001", "name": "개발팀A"})
        cursor.account = {"team_id": "TE001"}
        with _purging(cursor), self.assertRaises(PermissionDenied):
            repositories.OpsPurgeRepository.purge_team(
                team_id="TE001", actor_account_id="UA002", confirm_name="개발팀A"
            )

    def test_없는_팀은_알려준다(self):
        cursor = _Cursor(team=None)
        with _purging(cursor), self.assertRaises(RecordNotFound):
            repositories.OpsPurgeRepository.purge_team(
                team_id="TE999", actor_account_id="UA001", confirm_name="아무거나"
            )


class AccountPurgeGuardTests(SimpleTestCase):
    def _account(self, **over):
        base = {
            "account_id": "UA003",
            "email": "someone@example.com",
            "display_name": "홍길동",
            "team_id": "TE001",
            "is_admin": False,
        }
        base.update(over)
        return base

    def test_이메일이_다르면_지우지_않는다(self):
        cursor = _Cursor(account=self._account())
        with _purging(cursor), self.assertRaises(PermissionDenied):
            repositories.OpsPurgeRepository.purge_account(
                account_id="UA003", actor_account_id="UA001", confirm_name="홍길동"
            )

    def test_본인_계정은_못_지운다(self):
        cursor = _Cursor(account=self._account())
        with _purging(cursor), self.assertRaises(PermissionDenied):
            repositories.OpsPurgeRepository.purge_account(
                account_id="UA003", actor_account_id="UA003", confirm_name="someone@example.com"
            )

    def test_팀_소유자는_소유자_변경이_먼저다(self):
        """`team.owner_account_id` 는 NOT NULL 이다 — 지우면 팀이 주인을 잃는다."""

        cursor = _Cursor(
            account=self._account(), owned_teams=[{"team_id": "TE001", "name": "개발팀A"}]
        )
        with _purging(cursor) as _, self.assertRaises(PermissionDenied) as caught:
            repositories.OpsPurgeRepository.purge_account(
                account_id="UA003", actor_account_id="UA001", confirm_name="someone@example.com"
            )
        self.assertIn("개발팀A", str(caught.exception), "어느 팀 때문인지 말해야 한다")

    def test_마지막_운영자는_못_지운다(self):
        """지우면 아무도 콘솔에 못 들어온다."""

        cursor = _Cursor(account=self._account(is_admin=True), admin_count=0)
        with _purging(cursor), self.assertRaises(PermissionDenied):
            repositories.OpsPurgeRepository.purge_account(
                account_id="UA003", actor_account_id="UA001", confirm_name="someone@example.com"
            )


class PurgeStepShapeTests(SimpleTestCase):
    """표 자체를 지킨다 — 순서가 곧 정확성이라 사람이 줄을 옮기면 깨진다."""

    def test_팀_삭제는_팀_행을_맨_마지막에_지운다(self):
        last = repositories._TEAM_PURGE_STEPS[-1]
        self.assertEqual(last[0], "팀")
        self.assertIn("DELETE FROM team WHERE", last[1])

    def test_계정_삭제는_계정_행을_맨_마지막에_지운다(self):
        last = repositories._ACCOUNT_PURGE_STEPS[-1]
        self.assertEqual(last[0], "계정")
        self.assertIn("DELETE FROM user_account WHERE", last[1])

    def test_팀_삭제가_계정을_지우지_않는다(self):
        """PM 결정: 팀만 없애고 사람은 무소속으로 남긴다."""

        sqls = " ".join(sql for _, sql in repositories._TEAM_PURGE_STEPS)
        self.assertNotIn("DELETE FROM user_account", sqls)
        self.assertIn("UPDATE user_account SET team_id = NULL", sqls)

    def test_감사_기록은_어느_쪽도_지우지_않는다(self):
        """대상이 사라져도 「누가 무엇을 했는가」는 남는 것이 감사의 뜻이다."""

        sqls = " ".join(
            sql
            for _, sql in (*repositories._TEAM_PURGE_STEPS, *repositories._ACCOUNT_PURGE_STEPS)
        )
        self.assertNotIn("audit_log", sqls)

    def test_대화를_지우면_체크포인트도_지운다(self):
        """thread_id 가 곧 대화 id 다 — 안 지우면 승인 대기가 유령으로 남는다."""

        for steps in (repositories._TEAM_PURGE_STEPS, repositories._ACCOUNT_PURGE_STEPS):
            sqls = " ".join(sql for _, sql in steps)
            for table in ("checkpoints", "checkpoint_writes", "checkpoint_blobs"):
                self.assertIn(f"DELETE FROM {table} ", sqls)

    def test_체크포인트_비교는_text_로_캐스트한다(self):
        """체크포인트 3종은 **langgraph 가 만든 테이블**이라 `thread_id` 가 `text`
        인데 우리 `chat_session.session_id` 는 `uuid` 다. 캐스트 없이 비교하면
        `operator does not exist: text = uuid` 로 통째로 실패한다.

        회귀 방지: 실제로 그렇게 나갔고, 화면에는 「데이터베이스 요청을 처리할 수
        없습니다」로만 보여서 원인이 안 드러났다(2026-08-19).

        ⚠ 이 검사는 **문자열을 본다.** 위 가드 테스트들이 가짜 커서를 쓰기
        때문에 SQL 이 실제로 도는지는 아무도 확인하지 않는다 — 그래서 이
        결함이 배포까지 갔다. 표를 고치면 실제 DB 로 한 번 돌려 볼 것.
        """

        for steps in (repositories._TEAM_PURGE_STEPS, repositories._ACCOUNT_PURGE_STEPS):
            for label, sql in steps:
                if "checkpoint" not in sql:
                    continue
                self.assertIn(
                    "session_id::text",
                    sql,
                    f"{label}: thread_id(text) 와 session_id(uuid) 를 그냥 비교할 수 없다",
                )
