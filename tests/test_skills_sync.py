"""skills/sync.py(SkillRegisterSyncMiddleware) 단위 테스트.

2026-08-26 새로 추가, 같은 날 전체 재스캔 → 단건 조회로 다시 씀 — `skill_register`
성공 직후 방금 쓴 스킬 하나만 다시 읽어 `skills_metadata`에 얹는다. 세션
도중 만든 스킬이 다음 모델 호출부터 바로 목록에 보이게 하면서도, 이미
등록된 스킬 전체를 매번 다시 내려받지 않는다.
"""

from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from services.agent_runtime.skills.sync import SkillRegisterSyncMiddleware, build_skill_register_sync

_METADATA_TARGET = "deepagents.middleware.skills._skill_metadata_from_response"


def _request(*, name: str, args: dict, state: dict | None = None, tool_call_id: str = "call-1") -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": args, "id": tool_call_id},
        tool=None,
        state=state if state is not None else {},
        runtime=None,
    )


class _FakeBackend:
    def __init__(self) -> None:
        self.download_calls: list[list[str]] = []

    def download_files(self, paths: list[str]):
        self.download_calls.append(paths)
        return [Mock()]  # 내용은 _skill_metadata_from_response를 patch해서 대신한다.


class BuildSkillRegisterSyncTests(SimpleTestCase):
    def test_returns_a_configured_middleware(self):
        backend = _FakeBackend()
        sync = build_skill_register_sync(backend=backend)

        self.assertIsInstance(sync, SkillRegisterSyncMiddleware)
        self.assertIs(sync._backend, backend)


class UnguardedToolPassthroughTests(SimpleTestCase):
    def test_other_tool_is_not_fetched(self):
        backend = _FakeBackend()
        sync = SkillRegisterSyncMiddleware(backend=backend)
        handler = Mock(return_value="handled")
        request = _request(name="read_file", args={"file_path": "/skills/team/x/SKILL.md"})

        result = sync.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        self.assertEqual(result, "handled")
        self.assertEqual(backend.download_calls, [])


class RegisterFailurePassthroughTests(SimpleTestCase):
    def test_error_result_is_not_fetched(self):
        """이름 충돌·권한 없음 등으로 등록이 거부됐으면 다시 읽을 게 없다."""
        backend = _FakeBackend()
        sync = SkillRegisterSyncMiddleware(backend=backend)
        error_message = ToolMessage(
            name="skill_register", content="이미 있는 이름입니다", tool_call_id="call-1", status="error"
        )
        handler = Mock(return_value=error_message)
        request = _request(
            name="skill_register",
            args={"scope": "PERSONAL", "name": "web-research", "description": "d", "body": "b"},
        )

        result = sync.wrap_tool_call(request, handler)

        self.assertIs(result, error_message)
        self.assertEqual(backend.download_calls, [])


class RegisterSuccessTests(SimpleTestCase):
    def test_fetches_only_the_one_skill_just_written(self):
        """전체 소스를 다시 스캔하지 않는다 — 방금 쓴 스킬 하나만 조회한다."""
        backend = _FakeBackend()
        sync = SkillRegisterSyncMiddleware(backend=backend)
        handler = Mock(return_value=ToolMessage(name="skill_register", content="등록됨", tool_call_id="call-1"))
        request = _request(
            name="skill_register",
            args={"scope": "PERSONAL", "name": "web-research", "description": "d", "body": "b"},
        )
        new_skill = {"name": "web-research", "path": "/skills/personal/web-research/SKILL.md", "description": "d"}

        with patch(_METADATA_TARGET, return_value=new_skill):
            sync.wrap_tool_call(request, handler)

        self.assertEqual(backend.download_calls, [["/skills/personal/web-research/SKILL.md"]])

    def test_team_scope_does_not_enter_agent_skill_metadata(self):
        backend = _FakeBackend()
        sync = SkillRegisterSyncMiddleware(backend=backend)
        ok_message = ToolMessage(name="skill_register", content="등록됨", tool_call_id="call-1")
        handler = Mock(return_value=ok_message)
        request = _request(
            name="skill_register",
            args={"scope": "TEAM", "name": "onboarding", "description": "d", "body": "b"},
        )

        with patch(_METADATA_TARGET, return_value={"name": "onboarding"}):
            result = sync.wrap_tool_call(request, handler)

        self.assertEqual(backend.download_calls, [])
        self.assertIs(result, ok_message)

    def test_new_skill_is_merged_into_existing_cached_list(self):
        backend = _FakeBackend()
        sync = SkillRegisterSyncMiddleware(backend=backend)
        ok_message = ToolMessage(name="skill_register", content="등록됨", tool_call_id="call-1")
        handler = Mock(return_value=ok_message)
        existing = {"name": "old-skill", "path": "/skills/personal/old-skill/SKILL.md", "description": "기존"}
        request = _request(
            name="skill_register",
            args={"scope": "PERSONAL", "name": "web-research", "description": "d", "body": "b"},
            state={"skills_metadata": [existing]},
        )
        new_skill = {"name": "web-research", "path": "/skills/personal/web-research/SKILL.md", "description": "d"}

        with patch(_METADATA_TARGET, return_value=new_skill):
            result = sync.wrap_tool_call(request, handler)

        self.assertIsInstance(result, Command)
        skills = result.update["skills_metadata"]
        self.assertEqual({s["name"] for s in skills}, {"old-skill", "web-research"})
        self.assertEqual(result.update["messages"], [ok_message])

    def test_registering_same_name_again_replaces_the_old_entry(self):
        """같은 이름을 수정 등록한 경우(설명이 바뀌는 등) 목록엔 새 항목
        하나만 남아야 한다 — 중복으로 쌓이면 안 된다."""
        backend = _FakeBackend()
        sync = SkillRegisterSyncMiddleware(backend=backend)
        handler = Mock(return_value=ToolMessage(name="skill_register", content="등록됨", tool_call_id="call-1"))
        old_entry = {"name": "web-research", "path": "/skills/personal/web-research/SKILL.md", "description": "구버전"}
        request = _request(
            name="skill_register",
            args={"scope": "PERSONAL", "name": "web-research", "description": "새 설명", "body": "b"},
            state={"skills_metadata": [old_entry]},
        )
        new_entry = {"name": "web-research", "path": "/skills/personal/web-research/SKILL.md", "description": "새 설명"}

        with patch(_METADATA_TARGET, return_value=new_entry):
            result = sync.wrap_tool_call(request, handler)

        skills = result.update["skills_metadata"]
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0]["description"], "새 설명")

    def test_download_failure_leaves_result_untouched(self):
        """방금 쓴 파일을 다시 못 읽으면(드문 경우) 억지로 갱신하지 않고
        원래 도구 결과를 그대로 돌려준다 — 스킬 자체는 이미 저장됐으니
        다음 세션엔 정상적으로 보인다."""
        backend = _FakeBackend()
        sync = SkillRegisterSyncMiddleware(backend=backend)
        ok_message = ToolMessage(name="skill_register", content="등록됨", tool_call_id="call-1")
        handler = Mock(return_value=ok_message)
        request = _request(
            name="skill_register",
            args={"scope": "PERSONAL", "name": "web-research", "description": "d", "body": "b"},
        )

        with patch(_METADATA_TARGET, return_value=None):
            result = sync.wrap_tool_call(request, handler)

        self.assertIs(result, ok_message)

    def test_missing_scope_or_name_skips_update(self):
        backend = _FakeBackend()
        sync = SkillRegisterSyncMiddleware(backend=backend)
        ok_message = ToolMessage(name="skill_register", content="등록됨", tool_call_id="call-1")
        handler = Mock(return_value=ok_message)
        request = _request(name="skill_register", args={})

        result = sync.wrap_tool_call(request, handler)

        self.assertIs(result, ok_message)
        self.assertEqual(backend.download_calls, [])
