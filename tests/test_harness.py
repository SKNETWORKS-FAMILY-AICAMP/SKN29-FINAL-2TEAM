"""레거시 Harness가 남긴 것들의 단위 테스트.

`run_agent()`(레거시 Loop)와 그 조립을 검증하던 테스트가 여기 있었다.
2026-08-22에 레거시 `agent`/`agent_tool` 스키마와 함께 그 실행기를 걷어내면서
같이 지웠다 — 챗 실행 검증은 `tests/test_chat.py`(API 경계)와
`tests/test_executor.py`·`tests/test_factory.py`(새 엔진)가 맡는다.

남은 것은 **엔진이 바뀌어도 그대로인 조각들**이다: 공통 스캐폴드 문구,
입력 요약, 내장 도구가 등록 직전에 거르는 날짜, 그리고 어느 엔진에서도
그대로 쓰이는 `_skill_register()` 핸들러.
"""

from unittest.mock import patch

from django.test import SimpleTestCase
from langgraph.store.memory import InMemoryStore

from services.harness import registry, scaffold, trace
from services.harness.registry import ToolInputError


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


class SkillRegisterDescriptionTests(SimpleTestCase):
    def test_uses_the_system_confirmation_card_instead_of_chat_confirmation(self):
        description = registry.BUILTIN_TOOLS["skill_register"].description

        self.assertIn("시스템 확인 카드", description)
        self.assertIn("채팅 답변", description)
        self.assertNotIn("승인 없이 즉시 활성", description)


class SkillRegisterTests(SimpleTestCase):
    """`_skill_register()` — 정본: 2026-08-20_16_Skill_Middleware_설계.md.

    2026-08-22 리팩터로 실제 저장·검증은 `services.agent_runtime.skills.service`가
    맡는다 — 그 모듈이 부르는 `StoreBackend`가 그래프 실행 컨텍스트 밖에서
    쓰려면 진짜 `BaseStore` 구현이 필요하다(`.get`/`.put`/`.search`/`.batch`
    전부). 손으로 만든 put-only 가짜 대신 langgraph가 제공하는 실제 인메모리
    구현(`InMemoryStore`)을 쓴다 — 프로토콜을 다시 흉내 내지 않아도 되고,
    실제 저장소와 동작이 어긋날 걱정이 없다.
    """

    def _fake_store(self):
        return patch("services.agent_runtime.memory.store.get_memory_store")

    def test_scope가_아니면_사유를_말하며_거부한다(self):
        with self.assertRaises(ToolInputError):
            registry._skill_register(
                account_id="AC001",
                team_id="TM001",
                account_role="leader",
                scope="ORG",
                name="foo",
                description="d",
                body="b",
            )

    def test_팀원이_팀_스킬을_요청하면_거부한다(self):
        with self.assertRaises(ToolInputError) as ctx:
            registry._skill_register(
                account_id="AC001",
                team_id="TM001",
                account_role="member",
                scope="TEAM",
                name="foo",
                description="d",
                body="b",
            )
        self.assertIn("팀장", str(ctx.exception))

    def test_팀장은_팀_스킬을_등록할_수_있다(self):
        with self._fake_store() as mock_get_store:
            mock_get_store.return_value = InMemoryStore()

            result = registry._skill_register(
                account_id="AC001",
                team_id="TM001",
                account_role="leader",
                scope="TEAM",
                name="jira-issue-registration",
                description="Jira 이슈 등록 절차",
                body="1. 프로젝트 키를 확인한다\n2. 이슈를 만든다",
            )

        self.assertEqual(result["scope"], "TEAM")
        self.assertEqual(result["path"], "/skills/team/jira-issue-registration/SKILL.md")

    def test_개인_스킬은_역할과_무관하게_등록된다(self):
        with self._fake_store() as mock_get_store:
            store = InMemoryStore()
            mock_get_store.return_value = store

            result = registry._skill_register(
                account_id="AC001",
                team_id="TM001",
                account_role="member",
                scope="PERSONAL",
                name="my-note-taking",
                description="회의록 정리 절차",
                body="회의록을 이렇게 정리한다",
            )

        self.assertEqual(result["scope"], "PERSONAL")
        self.assertIsNotNone(store.get(("skill", "personal", "AC001"), result["path"]))

    def test_잘못된_이름은_거부한다(self):
        for bad_name in ("Foo-Bar", "-foo", "foo-", "foo--bar", "a" * 65, ""):
            with self.subTest(bad_name=bad_name):
                with self._fake_store() as mock_get_store:
                    mock_get_store.return_value = InMemoryStore()
                    with self.assertRaises(ToolInputError):
                        registry._skill_register(
                            account_id="AC001",
                            team_id="TM001",
                            account_role="leader",
                            scope="PERSONAL",
                            name=bad_name,
                            description="d",
                            body="b",
                        )

    def test_빈_설명이나_본문은_거부한다(self):
        with self._fake_store() as mock_get_store:
            mock_get_store.return_value = InMemoryStore()
            with self.assertRaises(ToolInputError):
                registry._skill_register(
                    account_id="AC001", team_id="TM001", account_role="leader",
                    scope="PERSONAL", name="foo", description="  ", body="b",
                )
        with self._fake_store() as mock_get_store:
            mock_get_store.return_value = InMemoryStore()
            with self.assertRaises(ToolInputError):
                registry._skill_register(
                    account_id="AC001", team_id="TM001", account_role="leader",
                    scope="PERSONAL", name="foo", description="d", body="   ",
                )

    def test_이름이_겹치면_거부한다(self):
        """2026-08-22 추가 — 이전에는 같은 이름으로 다시 등록하면 조용히
        덮어썼다. 설정 화면과 로직을 합치면서 "거부하고 알려준다"로
        정했다(업로드/직접 작성 둘 다 같은 규칙)."""
        with self._fake_store() as mock_get_store:
            mock_get_store.return_value = InMemoryStore()
            registry._skill_register(
                account_id="AC001", team_id="TM001", account_role="leader",
                scope="PERSONAL", name="dup-skill", description="d", body="b",
            )
            with self.assertRaises(ToolInputError) as ctx:
                registry._skill_register(
                    account_id="AC001", team_id="TM001", account_role="leader",
                    scope="PERSONAL", name="dup-skill", description="d2", body="b2",
                )
        self.assertIn("이미", str(ctx.exception))

    def test_저장한_내용은_이름_설명이_있는_frontmatter다(self):
        with self._fake_store() as mock_get_store:
            store = InMemoryStore()
            mock_get_store.return_value = store

            registry._skill_register(
                account_id="AC001",
                team_id="TM001",
                account_role="leader",
                scope="PERSONAL",
                name="my-skill",
                description="설명입니다",
                body="본문 절차",
            )

        item = store.get(("skill", "personal", "AC001"), "/skills/personal/my-skill/SKILL.md")
        content = item.value["content"]
        self.assertTrue(content.startswith("---\n"))
        self.assertIn("name: my-skill", content)
        self.assertIn("description:", content)
        self.assertIn("본문 절차", content)

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
