"""`services.agent_runtime.skills.registration` — 정본: 03_스킬_검증_등록_설계.md.

`run_checking`/`run_publishing`은 Store만 건드리고(`skill_jobs.py`의 실제 DB
계층은 안 씀) — `test_harness.py::SkillRegisterTests`와 같은 이유로 langgraph
실제 인메모리 구현(`InMemoryStore`)을 쓴다. `SkillRegistrationJobRepository`
(raw SQL 계층)는 여기서 다시 흉내 내지 않는다 — 실제 컨테이너에서 직접
확인했다("얇은 종단 경로" 검증, 03_스킬_검증_등록_설계.md 작업기록).
"""

from unittest.mock import patch

from django.test import SimpleTestCase
from langgraph.store.memory import InMemoryStore

from services.agent_runtime.skills.registration import (
    CheckingFailure,
    SkillRegistrationService,
    run_checking,
    run_publishing,
)
from services.agent_runtime.skills.service import SkillError


def _fake_store():
    return patch("services.agent_runtime.memory.store.get_memory_store")


def _job(**overrides):
    base = {
        "job_id": "job-test",
        "account_id": "AC001",
        "team_id": "TM001",
        "skill_name": "my-skill",
        "operation": "CREATE",
        "candidate_document": {
            "name": "my-skill",
            "description": "설명입니다",
            "body": "본문 절차",
            "enabled": True,
        },
        "candidate_hash": None,
        "base_content_hash": None,
    }
    base.update(overrides)
    if base["candidate_hash"] is None:
        from services.agent_runtime.skills.registration import _canonical_hash

        base["candidate_hash"] = _canonical_hash(base["candidate_document"])
    return base


class EnqueueTests(SimpleTestCase):
    def test_잘못된_이름은_job을_안_만들고_바로_거부한다(self):
        with _fake_store() as mock_get_store:
            mock_get_store.return_value = InMemoryStore()
            with self.assertRaises(SkillError):
                SkillRegistrationService.enqueue(
                    account_id="AC001", team_id="TM001",
                    name="Bad Name", description="d", body="b",
                )

    def test_기존_스킬이_있으면_UPDATE로_판정한다(self):
        with _fake_store() as mock_get_store:
            store = InMemoryStore()
            mock_get_store.return_value = store
            from services.agent_runtime.skills.service import create_personal_skill

            create_personal_skill(
                "AC001", team_id="TM001", name="existing-skill",
                description="원래 설명", body="원래 본문",
            )

            with patch(
                "services.agent_runtime.skills.registration.SkillRegistrationJobRepository"
            ) as mock_repo:
                mock_repo.create.return_value = ({"job_id": "j1", "status": "QUEUED", "stage": "WAITING"}, True)
                SkillRegistrationService.enqueue(
                    account_id="AC001", team_id="TM001",
                    name="existing-skill", description="새 설명", body="새 본문",
                )

        call_kwargs = mock_repo.create.call_args.kwargs
        self.assertEqual(call_kwargs["operation"], "UPDATE")
        self.assertIsNotNone(call_kwargs["base_content_hash"])

    def test_없는_스킬이면_CREATE로_판정한다(self):
        with _fake_store() as mock_get_store:
            mock_get_store.return_value = InMemoryStore()
            with patch(
                "services.agent_runtime.skills.registration.SkillRegistrationJobRepository"
            ) as mock_repo:
                mock_repo.create.return_value = ({"job_id": "j1", "status": "QUEUED", "stage": "WAITING"}, True)
                SkillRegistrationService.enqueue(
                    account_id="AC001", team_id="TM001",
                    name="brand-new-skill", description="d", body="b",
                )

        call_kwargs = mock_repo.create.call_args.kwargs
        self.assertEqual(call_kwargs["operation"], "CREATE")
        self.assertIsNone(call_kwargs["base_content_hash"])


class RetryTests(SimpleTestCase):
    @patch("services.agent_runtime.skills.registration._evaluation_context", return_value=(1, "runtime", "tools"))
    @patch("services.agent_runtime.skills.registration.SkillRegistrationJobRepository")
    def test_보완_UI가_본문만_보내도_업로드_frontmatter와_enabled를_보존한다(
        self, repository, _context
    ):
        repository.get.return_value = {
            **_job(),
            "status": "FAILED",
            "operation": "CREATE",
            "candidate_document": {
                "name": "uploaded-skill",
                "description": "기존 설명",
                "body": "기존 본문",
                "enabled": False,
                "frontmatter": {
                    "license": "Internal",
                    "allowed-tools": ["document_search"],
                    "metadata": {"owner": "qa"},
                },
            },
        }
        repository.create.return_value = ({"job_id": "retry-1"}, True)

        SkillRegistrationService.retry(
            job_id="job-test",
            account_id="AC001",
            team_id="TM001",
            candidate_document={
                "name": "uploaded-skill-v2",
                "description": "보완 설명",
                "body": "보완 본문",
            },
        )

        candidate = repository.create.call_args.kwargs["candidate_document"]
        self.assertFalse(candidate["enabled"])
        self.assertEqual(candidate["frontmatter"]["license"], "Internal")
        self.assertEqual(candidate["frontmatter"]["allowed-tools"], ["document_search"])
        self.assertEqual(candidate["frontmatter"]["metadata"], {"owner": "qa"})

    @patch("services.agent_runtime.skills.registration._evaluation_context", return_value=(1, "runtime", "tools"))
    @patch("services.agent_runtime.skills.registration.SkillRegistrationJobRepository")
    def test_신규등록_retry는_기존_이름으로_바꿔도_UPDATE로_승격하지_않는다(
        self, repository, _context
    ):
        repository.get.return_value = {
            **_job(), "status": "FAILED", "operation": "CREATE",
        }
        repository.create.return_value = ({"job_id": "retry-1"}, True)
        result = SkillRegistrationService.retry(
            job_id="job-test", account_id="AC001", team_id="TM001",
            candidate_document={"name": "existing-skill", "description": "설명", "body": "절차"},
        )
        self.assertTrue(result.created)
        self.assertIsNone(repository.create.call_args.kwargs["base_content_hash"])

    @patch("services.agent_runtime.skills.registration.SkillRegistrationJobRepository")
    def test_기존스킬_UPDATE_retry에서는_이름을_바꿀_수_없다(self, repository):
        repository.get.return_value = {
            **_job(operation="UPDATE", base_content_hash="original-hash"),
            "status": "FAILED", "skill_name": "my-skill",
        }
        with self.assertRaisesRegex(SkillError, "이름을 바꿀 수 없습니다"):
            SkillRegistrationService.retry(
                job_id="job-test", account_id="AC001", team_id="TM001",
                candidate_document={"name": "renamed-skill", "description": "설명", "body": "절차"},
            )
        repository.create.assert_not_called()


class RunCheckingTests(SimpleTestCase):
    def test_형식이_틀리면_INVALID_SKILL_FORMAT(self):
        job = _job(candidate_document={"name": "Bad Name", "description": "d", "body": "b", "enabled": True})
        with _fake_store() as mock_get_store:
            mock_get_store.return_value = InMemoryStore()
            with self.assertRaises(CheckingFailure) as ctx:
                run_checking(job)
        self.assertEqual(ctx.exception.code, "INVALID_SKILL_FORMAT")

    def test_CREATE인데_이름이_이미_있으면_SKILL_NAME_CONFLICT(self):
        with _fake_store() as mock_get_store, patch(
            "services.agent_runtime.skills.registration._suggest_names",
            return_value=["focused-skill", "guided-skill"],
        ):
            store = InMemoryStore()
            mock_get_store.return_value = store
            from services.agent_runtime.skills.service import create_personal_skill

            create_personal_skill(
                "AC001", team_id="TM001", name="my-skill", description="d", body="b"
            )

            job = _job(operation="CREATE")
            with self.assertRaises(CheckingFailure) as ctx:
                run_checking(job)

        self.assertEqual(ctx.exception.code, "SKILL_NAME_CONFLICT")
        self.assertEqual(len(ctx.exception.details["suggested_names"]), 2)
        self.assertFalse(any(n == "my-skill" for n in ctx.exception.details["suggested_names"]))

    def test_CREATE이고_이름이_비어있으면_통과한다(self):
        job = _job(operation="CREATE")
        with _fake_store() as mock_get_store:
            mock_get_store.return_value = InMemoryStore()
            run_checking(job)  # 예외가 안 나면 통과

    def test_UPDATE인데_그_사이_원본이_바뀌면_STALE_CANDIDATE(self):
        with _fake_store() as mock_get_store:
            store = InMemoryStore()
            mock_get_store.return_value = store
            from services.agent_runtime.skills.service import create_personal_skill, update_personal_skill

            create_personal_skill(
                "AC001", team_id="TM001", name="my-skill", description="원래", body="원래 본문"
            )
            # job은 "원래" 상태를 base로 들고 있는데, 검증 도중 다른 경로로 바뀐다.
            job = _job(operation="UPDATE", base_content_hash="stale-hash-from-before")
            update_personal_skill("AC001", "my-skill", description="바뀜", body="바뀐 본문")

            with self.assertRaises(CheckingFailure) as ctx:
                run_checking(job)

        self.assertEqual(ctx.exception.code, "STALE_CANDIDATE")


class RunPublishingTests(SimpleTestCase):
    def test_평가_환경이_바뀌면_STALE_EVAL_CONTEXT(self):
        job = _job(
            base_catalog_revision=1,
            runtime_profile_version="runtime-a",
            tool_registry_version="tools-a",
        )
        with patch(
            "services.agent_runtime.skills.registration._evaluation_context",
            return_value=(2, "runtime-a", "tools-a"),
        ):
            with self.assertRaises(CheckingFailure) as ctx:
                run_publishing(job)
        self.assertEqual(ctx.exception.code, "STALE_EVAL_CONTEXT")

    def test_CREATE_재시도는_RETRY여도_새_스킬을_만든다(self):
        job = _job(operation="RETRY", retry_of_job_id="old-job", attempt=2)
        with _fake_store() as mock_get_store:
            mock_get_store.return_value = InMemoryStore()
            result = run_publishing(job)
        self.assertEqual(result["name"], "my-skill")

    def test_CREATE는_새_스킬을_만든다(self):
        job = _job(operation="CREATE")
        with _fake_store() as mock_get_store:
            store = InMemoryStore()
            mock_get_store.return_value = store
            result = run_publishing(job)

        self.assertEqual(result["name"], "my-skill")
        # StoreBackend 아래의 실제 key는 CompositeBackend가 route prefix를
        # 벗긴 namespace 상대경로다. 절대경로를 저장하면 설정 API에서는
        # 보여도 SkillsMiddleware의 ``ls('/skills/personal/')``에는 안 보인다.
        self.assertTrue(store.get(("skill", "personal", "AC001"), "/my-skill/SKILL.md"))

    def test_CREATE는_검증한_frontmatter를_그대로_게시한다(self):
        document = {
            "name": "my-skill",
            "description": "설명입니다",
            "body": "본문 절차",
            "enabled": True,
            "frontmatter": {
                "name": "my-skill",
                "description": "설명입니다",
                "license": "MIT",
                "allowed-tools": ["document_search"],
                "metadata": {"owner": "platform"},
            },
        }
        with _fake_store() as mock_get_store:
            mock_get_store.return_value = InMemoryStore()
            result = run_publishing(_job(candidate_document=document))
        self.assertEqual(result["frontmatter"]["license"], "MIT")
        self.assertEqual(result["frontmatter"]["allowed-tools"], ["document_search"])
        self.assertEqual(result["frontmatter"]["metadata"]["owner"], "platform")

    def test_CREATE한_스킬을_DeepAgents_스캐너가_찾는다(self):
        """등록 성공과 실제 채팅 노출을 한 테스트로 묶은 경로 회귀 테스트."""

        from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
        from deepagents.middleware.skills import _list_skills_with_errors
        from services.agent_runtime.skills.backend import (
            SKILLS_PERSONAL_PATH_PREFIX,
            personal_namespace,
        )

        job = _job(operation="CREATE")
        with _fake_store() as mock_get_store:
            store = InMemoryStore()
            mock_get_store.return_value = store
            run_publishing(job)

        backend = CompositeBackend(
            default=StateBackend(),
            routes={
                SKILLS_PERSONAL_PATH_PREFIX: StoreBackend(
                    namespace=lambda _rt: personal_namespace("AC001"), store=store
                )
            },
        )
        skills, error = _list_skills_with_errors(backend, SKILLS_PERSONAL_PATH_PREFIX)

        self.assertIsNone(error)
        self.assertEqual([skill["name"] for skill in skills], ["my-skill"])

    def test_UPDATE는_수정_전_비활성_상태를_유지한다(self):
        """§11 통과 절차 5번 — 비활성 스킬을 수정해 검증을 통과시켰다고
        자동으로 활성화하지 않는다."""
        with _fake_store() as mock_get_store:
            store = InMemoryStore()
            mock_get_store.return_value = store
            from services.agent_runtime.skills.service import create_personal_skill, update_personal_skill
            from services.agent_runtime.skills.registration import _current_personal_hash

            create_personal_skill(
                "AC001", team_id="TM001", name="my-skill", description="원래", body="원래 본문"
            )
            update_personal_skill("AC001", "my-skill", enabled=False)

            base_hash = _current_personal_hash("AC001", "my-skill")
            job = _job(operation="UPDATE", base_content_hash=base_hash)
            result = run_publishing(job)

        self.assertFalse(result["enabled"])
        self.assertIsNone(store.get(("skill", "personal", "AC001"), "/my-skill/SKILL.md"))
        self.assertIsNotNone(
            store.get(("skill", "inactive-personal", "AC001"), "/my-skill/SKILL.md")
        )

    def test_UPDATE_중_allowed_tools가_바뀌면_STALE_CANDIDATE(self):
        with _fake_store() as mock_get_store:
            mock_get_store.return_value = InMemoryStore()
            from services.agent_runtime.skills.registration import _current_personal_hash
            from services.agent_runtime.skills.service import create_personal_skill, update_personal_skill

            create_personal_skill(
                "AC001", team_id="TM001", name="my-skill", description="원래", body="원래 본문",
                frontmatter={"allowed-tools": ["document_search"]},
            )
            base_hash = _current_personal_hash("AC001", "my-skill")
            update_personal_skill(
                "AC001", "my-skill", frontmatter={"allowed-tools": ["task_list"]},
            )

            with self.assertRaises(CheckingFailure) as context:
                run_publishing(_job(operation="UPDATE", base_content_hash=base_hash))

        self.assertEqual(context.exception.code, "STALE_CANDIDATE")

    def test_등록_직전_후보_내용이_바뀌면_STALE_CANDIDATE(self):
        """candidate_hash 재확인(§11 1번) — job 행의 candidate_document와
        candidate_hash가 어긋나면(이론상 데이터 손상이나 재시도 오배선) 그
        자리에서 막는다."""
        job = _job(operation="CREATE", candidate_hash="deliberately-wrong-hash")
        with _fake_store() as mock_get_store:
            mock_get_store.return_value = InMemoryStore()
            with self.assertRaises(CheckingFailure) as ctx:
                run_publishing(job)
        self.assertEqual(ctx.exception.code, "STALE_CANDIDATE")
