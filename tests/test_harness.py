"""레거시 Harness가 남긴 것들의 단위 테스트.

`run_agent()`(레거시 Loop)와 그 조립을 검증하던 테스트가 여기 있었다.
2026-08-22에 레거시 `agent`/`agent_tool` 스키마와 함께 그 실행기를 걷어내면서
같이 지웠다 — 챗 실행 검증은 `tests/test_chat.py`(API 경계)와
`tests/test_executor.py`·`tests/test_factory.py`(새 엔진)가 맡는다.

남은 것은 **엔진이 바뀌어도 그대로인 조각들**이다: 입력 요약, 내장 도구가 등록 직전에 거르는 날짜, 그리고 어느 엔진에서도
그대로 쓰이는 `_skill_register()` 핸들러.
"""

from unittest.mock import patch

from django.test import SimpleTestCase
from langgraph.store.memory import InMemoryStore

from services.harness import registry, trace
from services.harness.registry import ToolInputError


class InputSummaryTests(SimpleTestCase):
    def test_긴_값은_잘라서_남긴다(self):
        summary = trace.summarize_input({"query": "가" * 500})

        self.assertLessEqual(len(summary), trace.INPUT_SUMMARY_MAX)
        self.assertIn("query=", summary)


class JiraCreateIssuesTests(SimpleTestCase):
    def _common_patches(self):
        return patch.object(registry, "_jira_credential_account_id", return_value="UA001")

    def test_선택한_프로젝트가_있으면_모델이_추측한_키를_무시한다(self):
        credential_patch = self._common_patches()
        with (
            patch.object(
                registry.ProjectSourceRepository,
                "get_for_project",
                return_value={"external_source_id": "KAN"},
            ),
            credential_patch,
            patch.object(
                registry,
                "create_jira_issues",
                return_value={"project_key": "KAN", "created": [{"key": "KAN-1"}], "failed": []},
            ) as mock_create,
        ):
            registry._jira_create_issues(
                account_id="UA002",
                proj_id="PJ002",
                project_key="TEAMHUN",
                issues=[{"title": "제목"}],
            )

        self.assertEqual(mock_create.call_args.kwargs["project_key"], "KAN")

    def test_프로젝트_문맥이_없으면_명시한_Jira_키를_사용한다(self):
        credential_patch = self._common_patches()
        with (
            credential_patch,
            patch.object(
                registry,
                "create_jira_issues",
                return_value={"project_key": "KAN", "created": [{"key": "KAN-1"}], "failed": []},
            ) as mock_create,
        ):
            registry._jira_create_issues(
                account_id="UA002",
                project_key="KAN",
                issues=[{"title": "제목"}],
            )

        self.assertEqual(mock_create.call_args.kwargs["project_key"], "KAN")

    def test_생성된_이슈가_없고_실패만_있으면_정상_완료로_처리하지_않는다(self):
        credential_patch = self._common_patches()
        with (
            patch.object(
                registry.ProjectSourceRepository,
                "get_for_project",
                return_value={"external_source_id": "KAN"},
            ),
            credential_patch,
            patch.object(
                registry,
                "create_jira_issues",
                return_value={
                    "project_key": "KAN",
                    "created": [],
                    "failed": [{"error_code": "validation", "reason": "생성 권한이 없습니다."}],
                },
            ),
        ):
            with self.assertRaises(ToolInputError) as ctx:
                registry._jira_create_issues(
                    account_id="UA002",
                    proj_id="PJ002",
                    issues=[{"title": "제목"}],
                )

        self.assertIn("Jira 이슈를 생성하지 못했습니다", str(ctx.exception))
        self.assertIn("생성 권한이 없습니다", str(ctx.exception))

    def test_담당자_지시가_없으면_미배정으로_생성한다(self):
        with (
            self._common_patches(),
            patch.object(registry, "_fill_default_jira_assignee") as mock_fill,
            patch.object(
                registry,
                "create_jira_issues",
                return_value={"project_key": "KAN", "created": [{"key": "KAN-1"}], "failed": []},
            ) as mock_create,
        ):
            registry._jira_create_issues(
                account_id="UA002",
                project_key="KAN",
                issues=[{"title": "제목", "assignee_account_id": ""}],
            )

        mock_fill.assert_not_called()
        self.assertEqual(mock_create.call_args.kwargs["issues"][0]["assignee_account_id"], "")

    def test_본인_배정을_명시하면_요청자_Jira_계정을_채운다(self):
        filled = [{"title": "제목", "assignee_account_id": "jira-account-id"}]
        with (
            self._common_patches(),
            patch.object(registry, "_fill_default_jira_assignee", return_value=filled) as mock_fill,
            patch.object(
                registry,
                "create_jira_issues",
                return_value={"project_key": "KAN", "created": [{"key": "KAN-1"}], "failed": []},
            ) as mock_create,
        ):
            registry._jira_create_issues(
                account_id="UA002",
                project_key="KAN",
                assign_to_requester=True,
                issues=[{"title": "제목"}],
            )

        mock_fill.assert_called_once_with(
            requester_account_id="UA002",
            credential_account_id="UA001",
            issues=[{"title": "제목"}],
        )
        self.assertEqual(mock_create.call_args.kwargs["issues"], filled)


class TaskDestinationDescriptionTests(SimpleTestCase):
    def test_task_registration_is_not_a_jira_prerequisite(self):
        description = registry.BUILTIN_TOOLS["task_register"].description

        self.assertIn("Jira 등록의 선행 단계가 아니다", description)
        self.assertIn("Jira만 명시했다면", description)
        self.assertNotIn("Jira 보다 먼저", description)

    def test_jira_only_request_does_not_add_platform_registration(self):
        description = registry.BUILTIN_TOOLS["jira_create_issues"].description

        self.assertIn("Jira 등록을 명시했다면 이 도구를 직접 사용", description)
        self.assertIn("task_register", description)
        self.assertIn("함께 등록하라는 요청이 없으면", description)


class DocumentSearchDescriptionTests(SimpleTestCase):
    def test_requires_targeted_followup_and_direct_evidence(self):
        description = registry.BUILTIN_TOOLS["document_search"].description

        self.assertIn("하위 항목을 각각 구체적으로 다시 검색", description)
        self.assertIn("작업 공수 기간", description)
        self.assertIn("top_k=20", description)
        self.assertIn("직접 반환된 문장에서 값을 확인한 사실만", description)


class SkillRegisterDescriptionTests(SimpleTestCase):
    def test_uses_the_system_confirmation_card_instead_of_chat_confirmation(self):
        description = registry.BUILTIN_TOOLS["skill_register"].description

        self.assertIn("시스템 확인 카드", description)
        self.assertIn("채팅 답변", description)
        self.assertNotIn("승인 없이 즉시 활성", description)

    def test_등록_완료가_아니라_검증_시작이라고_말한다(self):
        """§16 "모델이 job 생성 직후 등록 완료라고 안내하지 않는다"를 도구
        설명 자체에 못박는다 — 모델은 이 텍스트만 보고 판단하므로, 여기 없으면
        아무리 워커·job이 맞아도 모델이 "등록했습니다"라고 말할 수 있다."""
        description = registry.BUILTIN_TOOLS["skill_register"].description

        self.assertIn("등록 완료가 아니라 검증 시작", description)
        self.assertNotIn("scope", description.lower())

    def test_입력_스키마에_scope가_없다(self):
        schema = registry.BUILTIN_TOOLS["skill_register"].input_schema
        self.assertNotIn("scope", schema["properties"])
        self.assertEqual(set(schema["required"]), {"name", "description", "body"})


class _FakeSkillJobRepository:
    """`SkillRegistrationJobRepository.create()`의 관찰 가능한 계약만 흉내 낸
    인메모리 가짜(2026-08-26) — `_skill_register()`가 검증 job **생성**을
    요청하는 시점의 로직(형식 검사, CREATE/UPDATE 판정, "열린 job은 하나")만
    검증한다.

    `backend/db/skill_jobs.py`의 실제 SQL(FOR UPDATE SKIP LOCKED, lease,
    부분 유니크 인덱스 등)은 여기서 다시 흉내 내지 않는다 — 이 저장소의
    다른 raw-SQL 테스트들(`test_evaluation_db.py`)이 쓰는 손으로 만든
    커서 mock과 같은 이유로, 여기서는 그 계층까지 검증하는 대신 워커/DB
    쪽은 실제 컨테이너에서 직접 확인했다(설계 문서 "얇은 종단 경로" 검증).
    """

    def __init__(self):
        self._open: dict[tuple[str, str], dict] = {}
        self._seq = 0

    def create(self, *, account_id, team_id, skill_name, operation, candidate_document,
               candidate_hash, base_content_hash, source_session_id, idempotency_key,
               retry_of_job_id=None, base_catalog_revision=None,
               runtime_profile_version=None, tool_registry_version=None):
        key = (account_id, skill_name)
        existing = self._open.get(key)
        if existing is not None:
            return existing, False
        self._seq += 1
        job = {
            "job_id": f"fake-job-{self._seq}",
            "account_id": account_id,
            "team_id": team_id,
            "skill_name": skill_name,
            "operation": operation,
            "candidate_document": candidate_document,
            "candidate_hash": candidate_hash,
            "base_content_hash": base_content_hash,
            "base_catalog_revision": base_catalog_revision,
            "runtime_profile_version": runtime_profile_version,
            "tool_registry_version": tool_registry_version,
            "source_session_id": source_session_id,
            "status": "QUEUED",
            "stage": "WAITING",
        }
        self._open[key] = job
        return job, True


class SkillRegisterTests(SimpleTestCase):
    """`_skill_register()` — 정본: 03_스킬_검증_등록_설계.md §5.

    **2026-08-26 재작성.** 이 도구는 더 이상 SKILL.md를 즉시 쓰지 않고
    `skill_registration_job`을 만든다(§6). `services.agent_runtime.skills.
    service`가 여전히 부르는 `StoreBackend`는 이름 충돌 판정(CREATE/UPDATE
    구분)에 쓰이므로 이전처럼 langgraph 실제 인메모리 구현(`InMemoryStore`)을
    쓰고, job 생성 자체는 위 `_FakeSkillJobRepository`로 대체한다.
    """

    def _fake_store(self):
        return patch("services.agent_runtime.memory.store.get_memory_store")

    def _fake_jobs(self):
        return patch(
            "services.agent_runtime.skills.registration.SkillRegistrationJobRepository",
            new=_FakeSkillJobRepository(),
        )

    def test_scope_인자는_더_이상_받지_않는다(self):
        with self.assertRaises(TypeError):
            registry._skill_register(
                account_id="AC001",
                team_id="TM001",
                scope="PERSONAL",
                name="foo",
                description="d",
                body="b",
            )

    def test_개인_스킬_검증_job을_만든다(self):
        with self._fake_store() as mock_get_store, self._fake_jobs():
            mock_get_store.return_value = InMemoryStore()

            result = registry._skill_register(
                account_id="AC001",
                team_id="TM001",
                session_id="SESS001",
                name="my-note-taking",
                description="회의록 정리 절차",
                body="회의록을 이렇게 정리한다",
            )

        self.assertEqual(result["status"], "QUEUED")
        self.assertEqual(result["stage"], "WAITING")
        self.assertIn("job_id", result)

    def test_반환값에_저장_경로가_없다(self):
        """§5 "반환값" — 아직 파일이 없으므로 `path`를 안 돌려준다."""
        with self._fake_store() as mock_get_store, self._fake_jobs():
            mock_get_store.return_value = InMemoryStore()
            result = registry._skill_register(
                account_id="AC001", team_id="TM001",
                name="foo", description="d", body="b",
            )
        self.assertNotIn("path", result)
        self.assertNotIn("scope", result)

    def test_잘못된_이름은_거부한다(self):
        for bad_name in ("Foo-Bar", "-foo", "foo-", "foo--bar", "a" * 65, ""):
            with self.subTest(bad_name=bad_name):
                with self._fake_store() as mock_get_store, self._fake_jobs():
                    mock_get_store.return_value = InMemoryStore()
                    with self.assertRaises(ToolInputError):
                        registry._skill_register(
                            account_id="AC001",
                            team_id="TM001",
                            name=bad_name,
                            description="d",
                            body="b",
                        )

    def test_빈_설명이나_본문은_거부한다(self):
        with self._fake_store() as mock_get_store, self._fake_jobs():
            mock_get_store.return_value = InMemoryStore()
            with self.assertRaises(ToolInputError):
                registry._skill_register(
                    account_id="AC001", team_id="TM001",
                    name="foo", description="  ", body="b",
                )
        with self._fake_store() as mock_get_store, self._fake_jobs():
            mock_get_store.return_value = InMemoryStore()
            with self.assertRaises(ToolInputError):
                registry._skill_register(
                    account_id="AC001", team_id="TM001",
                    name="foo", description="d", body="   ",
                )

    def test_같은_이름을_다시_요청하면_새_job_대신_열린_job을_돌려준다(self):
        """§9 "같은 사용자와 스킬 이름에는 열린 job을 하나만 허용한다" —
        예전(즉시 쓰기 시절)엔 두 번째 호출이 이름 충돌로 거부됐지만, 이제는
        첫 job이 아직 처리 중이라는 뜻이라 조용히 그 job을 다시 돌려준다.
        이름 충돌 자체는 워커의 `run_checking()`이 판정한다(더 이상 이
        핸들러의 책임이 아니다)."""
        with self._fake_store() as mock_get_store, self._fake_jobs():
            mock_get_store.return_value = InMemoryStore()
            first = registry._skill_register(
                account_id="AC001", team_id="TM001",
                name="dup-skill", description="d", body="b",
            )
            second = registry._skill_register(
                account_id="AC001", team_id="TM001",
                name="dup-skill", description="d2", body="b2",
            )
        self.assertEqual(first["job_id"], second["job_id"])
        self.assertIn("진행 중", second["message"])

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
