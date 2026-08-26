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


class 삭제_대상_누락_검사(SimpleTestCase):
    """`team_id`/`account_id` 를 든 테이블이 삭제 표에서 빠지지 않았는지 본다.

    **이 저장소에는 외래키가 하나도 없어서 CASCADE 가 없다.** 테이블을 더할 때마다
    세 곳(`_TEAM_PURGE_STEPS` · `_ACCOUNT_PURGE_STEPS` · `DB/reset_demo.sql`)에
    손으로 줄을 더해야 하는데, **실제로 두 번 빠뜨렸다** —

    - 2026-08-12: `reset_demo.sql` 에 Agent Platform 계열이 통째로 없었다.
      짧은 코드가 001 부터 다시 나가는 탓에 **새 팀이 옛 TE001 의 행을 물려받았다.**
    - 2026-08-25: 그 뒤 늘어난 `guardrail_provider`(team_id NOT NULL)·`mcp_call_note`
      가 `_TEAM_PURGE_STEPS` 에서, 넷이 `reset_demo.sql` 에서 빠져 있었다.

    사람이 기억해서 막을 수 없다는 것이 두 번으로 증명됐으므로 기계가 본다.
    스키마 파일을 읽어 대조하므로 DB 가 필요 없다.
    """

    #: 일부러 안 지우는 것. 지우지 않는 **이유**가 있어야 여기 들어온다.
    TEAM_KEEP = {
        "user_account",  # 팀만 없애고 사람은 무소속으로 남긴다(PM 결정 2026-08-19)
        "audit_log",     # 대상이 사라져도 「누가 무엇을 했는가」가 남는 것이 감사다
        "team",          # 표의 마지막 단계에서 지운다
    }
    ACCOUNT_KEEP = {
        "audit_log",
        "user_account",  # 표의 마지막 단계에서 지운다
    }
    #: `reset_demo.sql` 이 일부러 남기는 것 — 테넌트 데이터가 아니라 플랫폼 설정이다.
    RESET_KEEP = {"sys_setting", "sys_notice"}
    #: `reset_eval.sql`(평가용)이 `reset_demo.sql`(시연용)과 달리 **남기는** 것.
    #: 테넌트 그 자체와 재연결이 귀찮은 것들이다 — 평가 초기화의 목적이
    #: 「재로그인·재연결 없이 프로젝트와 문서만 갈아 끼우기」라서 남긴다.
    #: 이전 평가 성적표도 비교 기준이므로 입력 초기화와 함께 지우지 않는다.
    EVAL_KEEP = {
        "eval_run", "eval_case_result",
        "user_account", "team", "team_member", "team_folder",
        "member_invite", "user_person_link",
        "connector_conn",     # 이것을 남기려고 이 파일이 따로 있다
        "agents", "agent_versions", "agent_version_tools",
        "agent_version_subagents", "agent_favorites",
        "mcp_server", "mcp_tool", "guardrail_provider",
        "cal_event",          # 프로젝트와 무관하다
        "audit_log",          # 대상이 사라져도 「누가 무엇을 했는가」는 남는다
    }

    @staticmethod
    def _schema():
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        return (root / "DB" / "schema.sql").read_text(encoding="utf-8")

    @classmethod
    def _tables_with(cls, column):
        """`column` 을 칼럼으로 가진 앱 테이블 이름. `mock_hr` 는 뺀다."""
        import re

        found = []
        for m in re.finditer(r"CREATE TABLE ([a-z_.]+) \((.*?)\n\);", cls._schema(), re.S):
            name, body = m.group(1), m.group(2)
            if name.startswith("mock_hr."):
                continue
            if re.search(rf"\n    {column}\s", body):
                found.append(name)
        return found

    @staticmethod
    def _touched(steps):
        """표가 DELETE/UPDATE 하는 테이블 이름."""
        import re

        return {
            t
            for _, sql in steps
            for t in re.findall(r"(?:DELETE FROM|UPDATE)\s+([a-z_]+)", sql)
        }

    def test_팀_삭제가_team_id_를_든_테이블을_빠짐없이_덮는다(self):
        missing = sorted(
            set(self._tables_with("team_id"))
            - self._touched(repositories._TEAM_PURGE_STEPS)
            - self.TEAM_KEEP
        )
        self.assertEqual(
            missing,
            [],
            "team_id 를 들었는데 _TEAM_PURGE_STEPS 에 없다 — 팀을 지워도 남는다. "
            "지우지 않을 이유가 있으면 TEAM_KEEP 에 이유와 함께 적을 것",
        )

    def test_계정_삭제가_account_id_를_든_테이블을_빠짐없이_덮는다(self):
        missing = sorted(
            set(self._tables_with("account_id"))
            - self._touched(repositories._ACCOUNT_PURGE_STEPS)
            - self.ACCOUNT_KEEP
        )
        self.assertEqual(missing, [], "account_id 를 들었는데 _ACCOUNT_PURGE_STEPS 에 없다")

    def test_데모_초기화가_앱_테이블을_빠짐없이_비운다(self):
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        reset = (root / "DB" / "reset_demo.sql").read_text(encoding="utf-8")

        truncated = set()
        for m in re.finditer(r"TRUNCATE TABLE(.*?);", reset, re.S):
            truncated |= {x.strip() for x in m.group(1).replace("\n", " ").split(",") if x.strip()}

        app_tables = {
            name
            for name in re.findall(r"^CREATE TABLE ([a-z_.]+)", self._schema(), re.M)
            if not name.startswith("mock_hr.")
        }
        missing = sorted(app_tables - truncated - self.RESET_KEEP)
        self.assertEqual(
            missing,
            [],
            "reset_demo.sql 이 안 비우는 앱 테이블이 있다 — 옛 테넌트의 행이 남아 "
            "새 팀이 물려받는다(2026-08-12 실제 사고). 남길 이유가 있으면 "
            "RESET_KEEP 에 적고 스크립트 주석에도 남길 것",
        )

    def test_평가_초기화는_시연_초기화에서_남길_것만_뺀_것이다(self):
        """`reset_eval.sql` 을 스키마가 아니라 `reset_demo.sql` 과 대조한다.

        네 번째 손 관리 목록을 만들지 않으려는 것이다. 위 검사가 데모 쪽이
        빠짐없음을 이미 보증하므로, 평가 쪽은 **거기서 무엇을 뺐는지**만
        정확하면 된다. 테이블이 새로 늘면 데모 쪽 검사가 먼저 깨지고,
        데모에 줄을 더한 사람은 이 검사 때문에 평가 쪽에서도 지울지 남길지를
        **고르지 않을 수 없다.**
        """
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]

        def truncated(name):
            text = (root / "DB" / name).read_text(encoding="utf-8")
            # 주석 줄(`--`)에도 테이블 이름이 나오므로 먼저 걷어낸다.
            text = re.sub(r"^\s*--.*$", "", text, flags=re.M)
            found = set()
            for m in re.finditer(r"TRUNCATE TABLE(.*?);", text, re.S):
                found |= {x.strip() for x in m.group(1).replace("\n", " ").split(",") if x.strip()}
            return found

        demo = truncated("reset_demo.sql")
        evaluation = truncated("reset_eval.sql")

        self.assertEqual(
            sorted(evaluation - demo),
            [],
            "reset_eval.sql 이 reset_demo.sql 에 없는 테이블을 비운다 — 둘 중 하나가 틀렸다",
        )
        self.assertEqual(
            sorted(demo - evaluation),
            sorted(self.EVAL_KEEP),
            "평가 초기화가 남기는 목록이 EVAL_KEEP 과 다르다. 테이블을 새로 더했다면 "
            "reset_eval.sql 에서 지울지 EVAL_KEEP 에 이유와 함께 남길지 고를 것",
        )


class 서브쿼리_칼럼_실재_검사(SimpleTestCase):
    """삭제 SQL 의 서브쿼리가 **그 테이블에 없는 칼럼**을 고르지 않는지 본다.

    PostgreSQL 은 서브쿼리 안에서 못 찾은 이름을 **바깥 쿼리에서 다시 찾는다**
    (상관 서브쿼리). 그래서 오타가 오류로 드러나지 않고 **조건이 항상 참**이 된다.

    실제로 그렇게 나갔다 — `DELETE FROM mcp_tool WHERE server_id IN
    (SELECT server_id FROM mcp_server WHERE team_id = ...)`. `mcp_server` 의 PK 는
    `mcp_server_id` 라 `server_id` 가 바깥 `mcp_tool.server_id` 로 묶였고,
    조건이 `server_id IN (server_id)` 가 되어 **한 팀을 지울 때 모든 팀의 커스텀
    도구가 통째로 지워졌다**(2026-08-25 실제 DB 로 밟다가 발견, 2건 손실 후 복구).

    스키마 파일에서 칼럼을 읽으므로 DB 없이 돈다.
    """

    @staticmethod
    def _columns_by_table():
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        schema = (root / "DB" / "schema.sql").read_text(encoding="utf-8")
        out = {}
        for m in re.finditer(r"CREATE TABLE ([a-z_.]+) \((.*?)\n\);", schema, re.S):
            name, body = m.group(1), m.group(2)
            cols = set(re.findall(r"\n    ([a-z_]+)\s+[A-Za-z]", body))
            out[name.split(".")[-1]] = cols
        return out

    def test_서브쿼리가_고르는_칼럼이_그_테이블에_실재한다(self):
        import re

        columns = self._columns_by_table()
        problems = []
        for steps in (repositories._TEAM_PURGE_STEPS, repositories._ACCOUNT_PURGE_STEPS):
            for label, sql in steps:
                # 별칭 없는 단순 서브쿼리만 본다 — 별칭이 붙으면 모호하지 않다.
                for selected, table in re.findall(
                    r"SELECT\s+([a-z_]+)(?:::\w+)?\s+FROM\s+([a-z_]+)\s+WHERE", sql
                ):
                    known = columns.get(table)
                    if known and selected not in known:
                        problems.append(f"{label}: SELECT {selected} FROM {table}")

        self.assertEqual(
            problems,
            [],
            "서브쿼리가 그 테이블에 없는 칼럼을 고른다. PostgreSQL 은 이것을 "
            "바깥 쿼리의 칼럼으로 해석해 조건이 **항상 참**이 된다 — 오류 없이 "
            "다른 테넌트의 행까지 지운다",
        )
