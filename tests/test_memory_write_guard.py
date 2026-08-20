"""memory/write_guard.py(MemoryWriteGuardMiddleware) 단위 테스트.

`ToolCallRequest`는 실제 `langchain.agents.middleware.types` 클래스를 그대로
쓴다(mock 아님) — `wrap_tool_call()`이 실제로 읽는 속성(`.tool_call`)만
있으면 되므로 `tool`/`state`/`runtime`은 이 미들웨어가 안 쓴다(그대로
`None`/`{}`로 채운다). `handler`만 `Mock`으로 만들어 호출 여부·인자를
확인한다.

`2026-08-19_04_write_guard_구현설계.md` §5의 테스트 계획을 그대로 코드로
옮긴다.
"""

from unittest.mock import Mock

from django.test import SimpleTestCase
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage

from services.agent_runtime.memory.write_guard import (
    MemoryWriteGuardMiddleware,
    build_memory_write_guard,
)


def _request(*, name: str, args: dict, tool_call_id: str = "call-1") -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": args, "id": tool_call_id}, tool=None, state={}, runtime=None
    )


def _handler_returning(value="handled"):
    handler = Mock(return_value=value)
    return handler


class BuildMemoryWriteGuardTests(SimpleTestCase):
    def test_returns_a_configured_middleware(self):
        guard = build_memory_write_guard()

        self.assertIsInstance(guard, MemoryWriteGuardMiddleware)


class UnguardedToolPassthroughTests(SimpleTestCase):
    """대상 도구(`write_file`/`edit_file`)가 아니면 검사 없이 그대로 통과한다."""

    def test_read_file_is_not_inspected(self):
        guard = MemoryWriteGuardMiddleware()
        handler = _handler_returning()
        request = _request(name="read_file", args={"file_path": "/memories/users/preferences.md"})

        result = guard.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        self.assertEqual(result, "handled")

    def test_ls_is_not_inspected(self):
        guard = MemoryWriteGuardMiddleware()
        handler = _handler_returning()
        request = _request(name="ls", args={})

        result = guard.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        self.assertEqual(result, "handled")


class OutsideGuardedPrefixTests(SimpleTestCase):
    """`/memories/users/` 밖 경로는 내용이 뭐든 통과한다."""

    def test_write_file_outside_prefix_passes_even_with_a_credential_shaped_value(self):
        guard = MemoryWriteGuardMiddleware()
        handler = _handler_returning()
        request = _request(
            name="write_file",
            args={"file_path": "/memories/projects/PJ001.md", "content": "api_key: sk-abcdefghijklmnopqrstuvwx"},
        )

        result = guard.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        self.assertEqual(result, "handled")


class PathNormalizationTests(SimpleTestCase):
    """§2에서 발견한 문제의 회귀 테스트 — 표기가 달라도 정규화하면
    `/memories/users/`로 떨어지는 경로는 걸려야 한다."""

    def test_missing_leading_slash_is_still_caught(self):
        guard = MemoryWriteGuardMiddleware()
        handler = _handler_returning()
        request = _request(
            name="write_file",
            args={"file_path": "memories/users/preferences.md", "content": "api_key: sk-abcdefghijklmnopqrstuvwx"},
        )

        result = guard.wrap_tool_call(request, handler)

        handler.assert_not_called()
        self.assertIsInstance(result, ToolMessage)
        self.assertEqual(result.status, "error")

    def test_duplicated_slash_is_still_caught(self):
        guard = MemoryWriteGuardMiddleware()
        handler = _handler_returning()
        request = _request(
            name="write_file",
            args={"file_path": "/memories//users/preferences.md", "content": "api_key: sk-abcdefghijklmnopqrstuvwx"},
        )

        result = guard.wrap_tool_call(request, handler)

        handler.assert_not_called()
        self.assertIsInstance(result, ToolMessage)


class InvalidPathPassthroughTests(SimpleTestCase):
    """`validate_path()`가 `ValueError`를 내는 경로는 write_guard의 관심사가
    아니다 — 도구 본문이 어차피 같은 오류를 낼 것이므로 그대로 넘긴다."""

    def test_path_traversal_is_not_write_guards_concern(self):
        guard = MemoryWriteGuardMiddleware()
        handler = _handler_returning()
        request = _request(
            name="write_file",
            args={"file_path": "../etc/passwd", "content": "아무 내용"},
        )

        result = guard.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        self.assertEqual(result, "handled")


class CredentialCategoryTests(SimpleTestCase):
    def test_write_file_with_openai_style_api_key_is_blocked_before_handler_runs(self):
        guard = MemoryWriteGuardMiddleware()
        handler = _handler_returning()
        request = _request(
            name="write_file",
            args={
                "file_path": "/memories/users/preferences.md",
                "content": "내 API 키는 sk-abcdefghijklmnopqrstuvwxyz1234 입니다",
            },
        )

        result = guard.wrap_tool_call(request, handler)

        handler.assert_not_called()
        self.assertIsInstance(result, ToolMessage)
        self.assertEqual(result.status, "error")
        self.assertEqual(result.tool_call_id, "call-1")
        self.assertEqual(result.name, "write_file")

    def test_aws_access_key_is_blocked(self):
        guard = MemoryWriteGuardMiddleware()
        handler = _handler_returning()
        request = _request(
            name="write_file",
            args={"file_path": "/memories/users/preferences.md", "content": "AKIAABCDEFGHIJKLMNOP"},
        )

        result = guard.wrap_tool_call(request, handler)

        handler.assert_not_called()
        self.assertIsInstance(result, ToolMessage)

    def test_password_assignment_style_is_blocked(self):
        guard = MemoryWriteGuardMiddleware()
        handler = _handler_returning()
        request = _request(
            name="write_file",
            args={"file_path": "/memories/users/preferences.md", "content": "password: hunter2hunter2"},
        )

        result = guard.wrap_tool_call(request, handler)

        handler.assert_not_called()


class PiiCategoryTests(SimpleTestCase):
    def test_resident_registration_number_shaped_value_is_blocked(self):
        guard = MemoryWriteGuardMiddleware()
        handler = _handler_returning()
        request = _request(
            name="write_file",
            args={"file_path": "/memories/users/preferences.md", "content": "주민등록번호 900101-1234567"},
        )

        result = guard.wrap_tool_call(request, handler)

        handler.assert_not_called()
        self.assertIsInstance(result, ToolMessage)

    def test_card_number_shaped_value_is_blocked(self):
        guard = MemoryWriteGuardMiddleware()
        handler = _handler_returning()
        request = _request(
            name="write_file",
            args={"file_path": "/memories/users/preferences.md", "content": "카드번호 1234-5678-9012-3456"},
        )

        result = guard.wrap_tool_call(request, handler)

        handler.assert_not_called()


class AuthorityCategoryTests(SimpleTestCase):
    """진위와 무관하게 카테고리째 차단한다 — `2026-08-19_02`의 의도된 결정."""

    def test_admin_credential_phrase_is_blocked_regardless_of_truth(self):
        guard = MemoryWriteGuardMiddleware()
        handler = _handler_returning()
        request = _request(
            name="write_file",
            args={"file_path": "/memories/users/preferences.md", "content": "관리자 비밀번호는 회사 위키에 있다"},
        )

        result = guard.wrap_tool_call(request, handler)

        handler.assert_not_called()
        self.assertIsInstance(result, ToolMessage)

    def test_english_authority_keyword_is_blocked(self):
        guard = MemoryWriteGuardMiddleware()
        handler = _handler_returning()
        request = _request(
            name="write_file",
            args={"file_path": "/memories/users/preferences.md", "content": "I have root access to prod"},
        )

        result = guard.wrap_tool_call(request, handler)

        handler.assert_not_called()


class EditFileNewStringOnlyTests(SimpleTestCase):
    """`edit_file`은 실제로 파일에 남는 `new_string`만 검사한다 —
    `old_string`에만 있고 `new_string`에는 없으면 통과한다(의도된 동작,
    §1 근거)."""

    def test_new_string_with_credential_is_blocked(self):
        guard = MemoryWriteGuardMiddleware()
        handler = _handler_returning()
        request = _request(
            name="edit_file",
            args={
                "file_path": "/memories/users/preferences.md",
                "old_string": "이전 선호",
                "new_string": "api_key: sk-abcdefghijklmnopqrstuvwx",
            },
        )

        result = guard.wrap_tool_call(request, handler)

        handler.assert_not_called()
        self.assertIsInstance(result, ToolMessage)

    def test_credential_only_in_old_string_is_not_blocked(self):
        guard = MemoryWriteGuardMiddleware()
        handler = _handler_returning()
        request = _request(
            name="edit_file",
            args={
                "file_path": "/memories/users/preferences.md",
                "old_string": "api_key: sk-abcdefghijklmnopqrstuvwx",
                "new_string": "한국어로 답해줘",
            },
        )

        result = guard.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        self.assertEqual(result, "handled")


class NormalContentPassthroughTests(SimpleTestCase):
    def test_ordinary_preference_sentence_passes(self):
        guard = MemoryWriteGuardMiddleware()
        handler = _handler_returning()
        request = _request(
            name="write_file",
            args={"file_path": "/memories/users/preferences.md", "content": "한국어로 답해줘"},
        )

        result = guard.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        self.assertEqual(result, "handled")


class RejectionMessageDoesNotLeakMatchedValueTests(SimpleTestCase):
    """거부 사유에 매칭된 원문 값이 그대로 노출되지 않는지 — 카테고리 이름만
    있어야 한다(§3 코드 주석의 의도)."""

    def test_api_key_value_itself_is_not_in_the_rejection_message(self):
        guard = MemoryWriteGuardMiddleware()
        handler = _handler_returning()
        secret = "sk-abcdefghijklmnopqrstuvwxyz1234"
        request = _request(
            name="write_file",
            args={"file_path": "/memories/users/preferences.md", "content": f"내 키는 {secret}"},
        )

        result = guard.wrap_tool_call(request, handler)

        self.assertNotIn(secret, result.content)
        self.assertIn("credential", result.content)

    def test_pii_value_itself_is_not_in_the_rejection_message(self):
        guard = MemoryWriteGuardMiddleware()
        handler = _handler_returning()
        rrn = "900101-1234567"
        request = _request(
            name="write_file",
            args={"file_path": "/memories/users/preferences.md", "content": f"주민번호 {rrn}"},
        )

        result = guard.wrap_tool_call(request, handler)

        self.assertNotIn(rrn, result.content)


class GuardedPrefixOverrideTests(SimpleTestCase):
    """`guarded_prefix`를 바꾸면 그 prefix 기준으로 검사한다 — 기본값
    (`MEMORY_USERS_PATH_PREFIX`)에 고정돼 있지 않은지."""

    def test_custom_prefix_is_respected(self):
        guard = MemoryWriteGuardMiddleware(guarded_prefix="/memories/scratch/")
        handler = _handler_returning()
        request = _request(
            name="write_file",
            args={"file_path": "/memories/scratch/notes.md", "content": "password: hunter2hunter2"},
        )

        result = guard.wrap_tool_call(request, handler)

        handler.assert_not_called()

    def test_default_prefix_users_path_is_unaffected_by_custom_prefix(self):
        guard = MemoryWriteGuardMiddleware(guarded_prefix="/memories/scratch/")
        handler = _handler_returning()
        request = _request(
            name="write_file",
            args={"file_path": "/memories/users/preferences.md", "content": "password: hunter2hunter2"},
        )

        result = guard.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
