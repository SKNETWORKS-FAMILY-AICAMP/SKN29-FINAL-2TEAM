"""레거시 Harness가 남긴 것들의 단위 테스트.

`run_agent()`(레거시 Loop)와 그 조립을 검증하던 테스트가 여기 있었다.
2026-08-22에 레거시 `agent`/`agent_tool` 스키마와 함께 그 실행기를 걷어내면서
같이 지웠다 — 챗 실행 검증은 `tests/test_chat.py`(API 경계)와
`tests/test_executor.py`·`tests/test_factory.py`(새 엔진)가 맡는다.

남은 것은 **엔진이 바뀌어도 그대로인 조각들**이다: 공통 스캐폴드 문구,
입력 요약, 내장 도구가 등록 직전에 거르는 날짜.
"""

from unittest.mock import patch

from django.test import SimpleTestCase

from services.harness import scaffold, trace

class ScaffoldTests(SimpleTestCase):
    def test_공통_스캐폴드가_지켜야_할_것을_말한다(self):
        text = scaffold.compose(instruction="", max_iterations=10)

        self.assertIn("10회", text)
        self.assertIn("추측하지 않는다", text)
        # 매 답변 앞에 "계획:"이 붙던 것을 막는다(2026-08-11).
        self.assertIn("계획을 먼저 늘어놓지 않는다", text)
        # 도구가 없는 능력(번역·코딩 등)을 나열하던 것을 막는다.
        self.assertIn("가진 도구가 네가 할 수 있는 일", text)

    def test_에이전트_지시는_스캐폴드_뒤에_붙는다(self):
        """순서가 바뀌면 '추측 금지'가 개별 지시를 덮어쓴다."""

        text = scaffold.compose(instruction="표만 읽어라", max_iterations=3)

        self.assertLess(text.index("추측하지 않는다"), text.index("표만 읽어라"))

    def test_지시가_비어도_스캐폴드는_나온다(self):
        text = scaffold.compose(instruction="   ", max_iterations=5)

        self.assertIn("추측하지 않는다", text)
        self.assertNotIn("[이 에이전트의 지시]", text)


class InputSummaryTests(SimpleTestCase):
    def test_긴_값은_잘라서_남긴다(self):
        summary = trace.summarize_input({"query": "가" * 500})

        self.assertLessEqual(len(summary), trace.INPUT_SUMMARY_MAX)
        self.assertIn("query=", summary)


class TaskRegisterDateTests(SimpleTestCase):
    """등록 직전에 날짜를 거른다.

    문서에는 절대 날짜가 잘 없어서 「조치내역 확인 요청 후 5일 이내」 같은 상대
    표현이 뽑혀 나온다. 그게 `timestamptz` 컬럼까지 내려가 `InvalidDatetimeFormat`
    으로 죽었고, 한 트랜잭션이라 **승인한 18건이 전부 롤백됐다**(2026-08-12 QA
    시나리오 B — 그때 `task` 는 0 건이었다).
    """

    def test_상대_표현은_비운다(self):
        from backend.db.agent_platform import _date_or_none

        for text in ("조치내역 확인 요청 후 5일 이내", "종료단계(최종) 감리 종료 후 15일 이내", "미정", ""):
            with self.subTest(text=text):
                self.assertIsNone(_date_or_none(text))

    def test_절대_날짜는_그대로_둔다(self):
        from backend.db.agent_platform import _date_or_none

        self.assertEqual(_date_or_none("2026-08-20"), "2026-08-20")
        self.assertEqual(_date_or_none("2026-08-20T09:00:00"), "2026-08-20T09:00:00")
        self.assertIsNone(_date_or_none(None))

    def test_0_공수는_모른다는_뜻이다(self):
        """스키마가 `number` 면 모델은 모르는 값도 0 으로 채운다.

        실제로 문서에 공수가 없던 업무 7건이 전부 `effort = 0.00` 으로 들어갔다.
        0 시간짜리 업무는 없고, 그대로 두면 배정이 「공수 0 인 업무」로 계산한다.
        """

        from backend.db.agent_platform import _positive_or_none

        self.assertIsNone(_positive_or_none(0))
        self.assertIsNone(_positive_or_none(0.0))
        self.assertIsNone(_positive_or_none(""))
        self.assertIsNone(_positive_or_none("  "))
        self.assertIsNone(_positive_or_none(None))
        self.assertEqual(_positive_or_none(16), 16)
        self.assertEqual(_positive_or_none("백엔드"), "백엔드")

    def test_비운_것을_돌려줘야_사람이_안다(self):
        """조용히 버리면 「마감이 없는 업무」와 「마감을 못 읽은 업무」가 구별되지 않는다."""

        from backend.db import agent_platform

        cursor = _RegisterCursor()
        with patch.object(agent_platform, "database_connection", _fake_connection(cursor)), \
                patch.object(agent_platform, "_require_team", return_value="TM001"), \
                patch.object(agent_platform, "next_short_code", side_effect=["KM001", "TK001", "TK002"]):
            result = agent_platform.ProjectTaskRepository.register(
                proj_id="PJ001",
                account_id="UA001",
                tasks=[
                    {"title": "감리보고서 제출", "due_date": "조치내역 확인 요청 후 5일 이내"},
                    {"title": "착수 회의", "due_date": "2026-08-20"},
                ],
            )

        self.assertEqual(len(result["tasks"]), 2)
        self.assertEqual(result["dropped_fields"], [{"title": "감리보고서 제출", "fields": ["마감일"]}])
        self.assertEqual([row[6] for row in cursor.inserted], [None, "2026-08-20"])

    def test_모르는_값을_0으로_채워_보내면_비웠다고_알린다(self):
        """**모델이 모르는 공수를 채우는 값이 하필 `0`** 이다(`_positive_or_none`).

        회귀 방지: 예전엔 날짜만 돌려줬고 판정도 `if given` 이라, `0` 은 거짓이라
        두 번 걸러졌다. 그 결과 15건 전부 `effort_hours: 0` 으로 와서 전부 NULL 로
        저장됐는데 모델은 「0시간으로 등록했습니다」라고 답했다(2026-08-18 QA).
        """

        from backend.db import agent_platform

        cursor = _RegisterCursor()
        with patch.object(agent_platform, "database_connection", _fake_connection(cursor)),                 patch.object(agent_platform, "_require_team", return_value="TM001"),                 patch.object(agent_platform, "next_short_code", side_effect=["KM001", "TK001"]):
            result = agent_platform.ProjectTaskRepository.register(
                proj_id="PJ001",
                account_id="UA001",
                tasks=[{"title": "감리 착수", "effort_hours": 0, "required_role": "", "priority": "높음"}],
            )

        self.assertEqual(
            result["dropped_fields"],
            [{"title": "감리 착수", "fields": ["공수"]}],
            "0 으로 채워 보낸 공수를 비웠다고 알려야 한다",
        )
        # 빈 문자열은 「준 적 없음」이라 알릴 것이 없고, 준 값은 그대로 남는다.
        self.assertIsNone(cursor.inserted[0][3], "빈 역할은 NULL")
        self.assertIsNone(cursor.inserted[0][4], "0 공수는 NULL")
        self.assertEqual(cursor.inserted[0][7], "높음", "준 우선순위는 그대로")


class _RegisterCursor:
    """`register` 가 부르는 SQL 만 흉내낸다.

    쿼리를 구분한다 — 2026-08-19 에 `register` 가 「현재 판을 찾고」·「그 판에
    이미 있는 제목을 읽는」 두 조회를 더 하게 됐다. 전부 같은 행을 돌려주면
    판을 찾았는지 못 찾았는지가 구분되지 않는다.
    """

    def __init__(self):
        self.inserted = []
        #: 이 프로젝트에 이미 있는 판. None 이면 첫 등록이라 새로 만든다.
        self.existing_model = None
        #: 그 판에 이미 들어 있는 업무 제목.
        self.existing_titles = []
        self._last = ""

    def execute(self, sql, params=None):
        self._last = sql
        if "INSERT INTO task " in sql:
            self.inserted.append(params)

    def fetchone(self):
        if "FROM proj_know_model" in self._last:
            return self.existing_model
        return {"team_id": "TM001", "n": 0}

    def fetchall(self):
        if "SELECT task_name FROM task" in self._last:
            return [{"task_name": title} for title in self.existing_titles]
        return []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _fake_connection(cursor):
    class _Connection:
        def cursor(self):
            return cursor

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    return lambda: _Connection()

