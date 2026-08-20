"""`next_short_code` — **지워진 번호를 다시 주지 않는지**를 지킨다.

2026-08-19: 운영자 콘솔에 완전 삭제가 생기면서 처음으로 행이 사라질 수 있게
됐다. 그전까지는 삭제가 없어서 「살아 있는 행의 최대값 + 1」이 곧 유일한
번호였다. 실제로 `UA005` 를 지운 뒤 재가입자가 같은 `UA005` 를 받았고, 그러면
감사 기록의 「UA005 를 삭제했다」와 지금 살아 있는 `UA005` 가 **다른 사람**인데
id 로는 구별되지 않는다.
"""

from django.test import SimpleTestCase

from backend.db.codes import next_short_code
from backend.db.errors import IdSpaceExhausted


class _Cursor:
    """`next_short_code` 가 던지는 세 쿼리(잠금·살아있는 최대·지워진 최대)만 흉내낸다."""

    def __init__(self, *, live_max: int, purged_max: int = 0):
        self.live_max = live_max
        self.purged_max = purged_max
        self.queries: list[str] = []
        self._last = ""

    def execute(self, query, params=None):
        text = query if isinstance(query, str) else query.as_string(None)
        self._last = text
        self.queries.append(text)

    def fetchone(self):
        if "audit_log" in self._last:
            return {"coalesce": self.purged_max}
        if "pg_advisory_xact_lock" in self._last:
            return None
        return {"coalesce": self.live_max}


class NextShortCodeTests(SimpleTestCase):
    def test_지워진_번호를_다시_주지_않는다(self):
        """UA005 를 지웠으면 다음 가입자는 UA006 이다 — UA005 가 아니다."""

        cursor = _Cursor(live_max=4, purged_max=5)
        code = next_short_code(cursor, table="user_account", column="account_id", prefix="UA")
        self.assertEqual(code, "UA006")

    def test_삭제가_없으면_예전과_같다(self):
        cursor = _Cursor(live_max=4, purged_max=0)
        self.assertEqual(
            next_short_code(cursor, table="user_account", column="account_id", prefix="UA"),
            "UA005",
        )

    def test_살아있는_쪽이_더_크면_그쪽을_따른다(self):
        """옛 번호를 지웠어도 그 뒤로 더 큰 번호가 발급됐으면 거기서 이어간다."""

        cursor = _Cursor(live_max=9, purged_max=3)
        self.assertEqual(
            next_short_code(cursor, table="team", column="team_id", prefix="TE"),
            "TE010",
        )

    def test_삭제_기록도_함께_본다(self):
        """회귀 방지: 감사 기록을 안 보면 구멍이 그대로 다시 채워진다."""

        cursor = _Cursor(live_max=4, purged_max=5)
        next_short_code(cursor, table="user_account", column="account_id", prefix="UA")
        self.assertTrue(
            any("audit_log" in q for q in cursor.queries),
            "지워진 번호를 확인하지 않으면 재사용을 막을 수 없다",
        )

    def test_번호_공간이_다_차면_알려준다(self):
        cursor = _Cursor(live_max=999)
        with self.assertRaises(IdSpaceExhausted):
            next_short_code(cursor, table="user_account", column="account_id", prefix="UA")

    def test_접두사는_영문_두_글자여야_한다(self):
        cursor = _Cursor(live_max=0)
        for bad in ("U", "USR", "U1", "가나"):
            with self.subTest(prefix=bad), self.assertRaises(ValueError):
                next_short_code(cursor, table="user_account", column="account_id", prefix=bad)
