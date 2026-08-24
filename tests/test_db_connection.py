"""`backend/db/connection.py` — 연결 풀 구성 단위 테스트.

**DB 를 띄우지 않는다.** 여기서 보는 것은 풀을 *어떻게 만드는가*이고, 실제
트랜잭션 규칙(commit·rollback·반납)은 살아 있는 Postgres 로 따로 확인했다
(2026-08-24). 이 테스트가 막는 것은 그때 확인한 전제가 **조용히 사라지는** 것이다.

특히 `row_factory=dict_row` — 저장소 209곳이 전부 `row["컬럼"]` 으로 읽는다.
이 값이 빠지면 오류 메시지 없이 전부 튜플을 받아 `TypeError` 로 흩어진다.
"""

from unittest.mock import patch

from django.test import SimpleTestCase
from psycopg.rows import dict_row

from backend.db import connection as conn_module


class PoolConfigurationTests(SimpleTestCase):
    def setUp(self):
        # 풀은 프로세스 전역이라 앞선 테스트가 만들어 뒀을 수 있다.
        self._saved = conn_module._pool
        conn_module._pool = None

    def tearDown(self):
        conn_module._pool = self._saved

    def _build(self):
        """풀을 한 번 만들고 `(생성 인자, 그때 쓰인 클래스)` 를 돌려준다.

        클래스를 함께 주는 이유 — `check=ConnectionPool.check_connection` 처럼
        **클래스 자신의 속성**을 넘기는 인자가 있어서, 진짜 클래스와 비교하면
        패치가 풀린 뒤라 항상 어긋난다.
        """

        with patch.object(conn_module, "ConnectionPool") as pool_cls:
            with patch.object(conn_module.atexit, "register"):
                conn_module._get_pool()
        return pool_cls.call_args, pool_cls

    def test_행을_dict_로_받는다(self):
        """저장소 전체가 `row["컬럼"]` 으로 읽는다. 빠지면 조용히 다 깨진다."""

        call, _ = self._build()
        self.assertEqual(call.kwargs["kwargs"]["row_factory"], dict_row)

    def test_연결에_이름을_붙인다(self):
        """`pg_stat_activity` 에서 우리 연결을 셀 수 있어야 한다 — 풀 크기를
        조정하거나 `max_connections` 를 점검할 때 그것 말고는 방법이 없다."""

        call, _ = self._build()
        self.assertEqual(call.kwargs["kwargs"]["application_name"], "halil")

    def test_빌려주기_전에_살아_있는지_본다(self):
        """유휴 연결은 RDS·NAT·방화벽이 조용히 끊는다. 확인 없이 내주면 그
        사실이 엉뚱한 질의에서 처음 드러난다."""

        call, pool_cls = self._build()
        self.assertIs(call.kwargs["check"], pool_cls.check_connection)

    def test_생성자가_DB_를_기다리지_않는다(self):
        """`open=True` 는 배경 스레드로 연결한다 — DB 가 죽어 있어도 프로세스는
        떠야 한다. 여기서 막히면 헬스체크조차 못 뜬다."""

        call, _ = self._build()
        self.assertTrue(call.kwargs["open"])

    def test_상한과_대기_시간이_정해져_있다(self):
        """워커 프로세스마다 이만큼 잡는다. 상한이 없으면 사용자가 몰릴 때
        `max_connections` 에 부딪힌다."""

        call, _ = self._build()
        self.assertEqual(call.kwargs["max_size"], conn_module._POOL_MAX_SIZE)
        self.assertEqual(call.kwargs["timeout"], conn_module._POOL_TIMEOUT_SECONDS)

    def test_풀은_한_번만_만든다(self):
        """호출마다 만들면 풀을 쓰는 뜻이 없다 — 그게 고치려던 문제다."""

        with patch.object(conn_module, "ConnectionPool") as pool_cls:
            with patch.object(conn_module.atexit, "register"):
                first = conn_module._get_pool()
                second = conn_module._get_pool()

        self.assertEqual(pool_cls.call_count, 1)
        self.assertIs(first, second)

    def test_종료할_때_닫도록_등록한다(self):
        """풀은 배경 스레드를 띄운다. 안 닫으면 관리 명령·스크립트가 끝날 때마다
        「couldn't stop thread」가 줄줄이 찍힌다."""

        with patch.object(conn_module, "ConnectionPool"):
            with patch.object(conn_module.atexit, "register") as register:
                conn_module._get_pool()

        register.assert_called_once()
