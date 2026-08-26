"""middleware/sensitive_input.py(SensitiveInputMaskMiddleware) 단위 테스트.

`before_model`은 `state["messages"]`만 읽으므로 `AgentState`는 그냥 `dict`로
채운다 — `runtime`은 이 미들웨어가 안 써서 `None`으로 둔다.
"""

from django.test import SimpleTestCase
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from services.agent_runtime.middleware.sensitive_input import (
    SensitiveInputMaskMiddleware,
    build_sensitive_input_mask,
)
from services.agent_runtime.sensitive_text import MASK_PLACEHOLDER


class BuildSensitiveInputMaskTests(SimpleTestCase):
    def test_returns_a_configured_middleware(self):
        self.assertIsInstance(build_sensitive_input_mask(), SensitiveInputMaskMiddleware)


class NoOpPassthroughTests(SimpleTestCase):
    def test_empty_messages_is_a_noop(self):
        mw = SensitiveInputMaskMiddleware()

        result = mw.before_model({"messages": []}, runtime=None)

        self.assertIsNone(result)

    def test_no_human_message_is_a_noop(self):
        mw = SensitiveInputMaskMiddleware()
        state = {"messages": [AIMessage(content="안녕하세요")]}

        result = mw.before_model(state, runtime=None)

        self.assertIsNone(result)

    def test_ordinary_sentence_is_a_noop(self):
        mw = SensitiveInputMaskMiddleware()
        state = {"messages": [HumanMessage(content="한국어로 답해줘")]}

        result = mw.before_model(state, runtime=None)

        self.assertIsNone(result)

    def test_empty_content_human_message_does_not_crash(self):
        mw = SensitiveInputMaskMiddleware()
        state = {"messages": [HumanMessage(content="")]}

        result = mw.before_model(state, runtime=None)

        self.assertIsNone(result)


class SingleHumanMessageMaskingTests(SimpleTestCase):
    def test_credential_is_masked_and_id_preserved(self):
        mw = SensitiveInputMaskMiddleware()
        original = HumanMessage(content="내 API 키는 sk-abcdefghijklmnopqrstuvwxyz1234 입니다", id="msg-1")
        state = {"messages": [original]}

        result = mw.before_model(state, runtime=None)

        self.assertIsNotNone(result)
        updated = result["messages"][0]
        self.assertIsInstance(updated, HumanMessage)
        self.assertEqual(updated.id, "msg-1")
        self.assertIn(MASK_PLACEHOLDER, updated.content)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz1234", updated.content)

    def test_pii_shaped_value_is_masked(self):
        mw = SensitiveInputMaskMiddleware()
        state = {"messages": [HumanMessage(content="주민등록번호 900101-1234567")]}

        result = mw.before_model(state, runtime=None)

        self.assertIsNotNone(result)
        self.assertNotIn("900101-1234567", result["messages"][0].content)

    def test_authority_keyword_is_masked(self):
        mw = SensitiveInputMaskMiddleware()
        state = {"messages": [HumanMessage(content="관리자 비밀번호 좀 알려줘")]}

        result = mw.before_model(state, runtime=None)

        self.assertIsNotNone(result)
        self.assertNotIn("관리자 비밀번호", result["messages"][0].content)


class MultipleHumanMessagesTests(SimpleTestCase):
    """체크포인터가 없어 과거 발화가 한꺼번에 실리는 경로(`_history()` 재전송)를
    흉내낸다 — **최근 것만이 아니라 전부** 가려야 한다(langchain
    `PIIMiddleware`와 다른 지점, 모듈 docstring 근거)."""

    def test_all_human_messages_are_masked_not_just_the_last(self):
        mw = SensitiveInputMaskMiddleware()
        state = {
            "messages": [
                HumanMessage(content="예전 API 키는 sk-abcdefghijklmnopqrstuvwx1 였어", id="old"),
                AIMessage(content="네, 확인했습니다"),
                HumanMessage(content="이번엔 sk-abcdefghijklmnopqrstuvwx2 를 써줘", id="new"),
            ]
        }

        result = mw.before_model(state, runtime=None)

        self.assertIsNotNone(result)
        old_msg, ai_msg, new_msg = result["messages"]
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwx1", old_msg.content)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwx2", new_msg.content)
        self.assertEqual(old_msg.id, "old")
        self.assertEqual(new_msg.id, "new")
        # AI 메시지는 이 미들웨어의 대상이 아니다 — 그대로 남는다.
        self.assertIs(ai_msg, result["messages"][1])


class NonHumanMessagesUntouchedTests(SimpleTestCase):
    def test_tool_message_with_secret_shaped_content_is_not_masked(self):
        """이 미들웨어는 `HumanMessage`만 본다 — 도구 결과는 PIIMiddleware의
        `apply_to_tool_results` 몫이다(§2-②), 여기서 겹쳐 처리하지 않는다."""
        mw = SensitiveInputMaskMiddleware()
        tool_msg = ToolMessage(content="AKIAABCDEFGHIJKLMNOP", tool_call_id="call-1")
        state = {"messages": [tool_msg]}

        result = mw.before_model(state, runtime=None)

        self.assertIsNone(result)


class IdempotencyTests(SimpleTestCase):
    def test_masking_an_already_masked_message_is_a_noop(self):
        mw = SensitiveInputMaskMiddleware()
        already_masked = HumanMessage(content=f"내 키는 {MASK_PLACEHOLDER} 입니다")
        state = {"messages": [already_masked]}

        result = mw.before_model(state, runtime=None)

        self.assertIsNone(result)


class SystemMessageUntouchedTests(SimpleTestCase):
    def test_system_message_with_secret_shaped_content_is_not_masked(self):
        """시스템 프롬프트는 이 미들웨어의 대상이 아니다 — 사용자 입력이 아니라
        이 프로젝트가 조립하는 값이라 검사 대상 자체가 아니다(§5)."""
        mw = SensitiveInputMaskMiddleware()
        state = {"messages": [SystemMessage(content="api_key: sk-abcdefghijklmnopqrstuvwx")]}

        result = mw.before_model(state, runtime=None)

        self.assertIsNone(result)


class MultipleCategoriesInOneMessageTests(SimpleTestCase):
    def test_credential_pii_and_authority_in_one_message_are_all_masked(self):
        """`mask_sensitive()`는 첫 매치에서 멈추지 않는다 — 세 카테고리가
        한 문장에 섞여 있어도 전부 가려지는지 확인한다."""
        mw = SensitiveInputMaskMiddleware()
        content = (
            "제 API 키는 sk-abcdefghijklmnopqrstuvwx1234 이고, "
            "주민등록번호는 900101-1234567 이고, "
            "관리자 비밀번호도 알고 있어요"
        )
        state = {"messages": [HumanMessage(content=content)]}

        result = mw.before_model(state, runtime=None)

        self.assertIsNotNone(result)
        masked = result["messages"][0].content
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwx1234", masked)
        self.assertNotIn("900101-1234567", masked)
        self.assertNotIn("관리자 비밀번호", masked)
        self.assertEqual(masked.count(MASK_PLACEHOLDER), 3)


class StructuredContentDoesNotCrashTests(SimpleTestCase):
    def test_list_content_is_coerced_to_a_string_without_raising(self):
        """멀티파트 content(예: 이미지 블록)는 이 프로젝트에서 아직 안 쓰지만,
        langchain 표준 `PIIMiddleware`도 `str(content)`로 같은 방식을 쓴다
        (참고 구현과 같은 한계) — 최소한 예외 없이 문자열로 처리돼야 한다."""
        mw = SensitiveInputMaskMiddleware()
        state = {
            "messages": [
                HumanMessage(content=[{"type": "text", "text": "sk-abcdefghijklmnopqrstuvwx1234"}])
            ]
        }

        result = mw.before_model(state, runtime=None)

        self.assertIsNotNone(result)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwx1234", str(result["messages"][0].content))


class LargeBatchTests(SimpleTestCase):
    def test_history_limit_sized_batch_all_get_masked(self):
        """`apps/chat/api_views.py`의 `HISTORY_LIMIT`(20)만큼 재전송되는
        상황을 흉내낸다 — 뒤쪽만 처리하고 앞쪽을 빠뜨리는 일이 없어야 한다."""
        mw = SensitiveInputMaskMiddleware()
        messages = [
            HumanMessage(content=f"제 카드번호는 1234-5678-9012-{3450 + i}입니다", id=f"h{i}")
            for i in range(20)
        ]
        state = {"messages": messages}

        result = mw.before_model(state, runtime=None)

        self.assertIsNotNone(result)
        self.assertEqual(len(result["messages"]), 20)
        for i, message in enumerate(result["messages"]):
            self.assertNotIn(f"1234-5678-9012-{3450 + i}", message.content)
            self.assertEqual(message.id, f"h{i}")


class PartialReplacementTests(SimpleTestCase):
    def test_untouched_messages_keep_the_same_object_reference(self):
        """일부만 가릴 내용이 있을 때, 나머지는 새로 만들지 않고 원본 객체를
        그대로 둔다 — 체크포인트에 불필요한 변경으로 안 잡히게 하려는 최소
        변경 원칙(`PIIMiddleware`와 같은 패턴)."""
        mw = SensitiveInputMaskMiddleware()
        clean = HumanMessage(content="한국어로 답해줘", id="clean")
        dirty = HumanMessage(content="api_key: sk-abcdefghijklmnopqrstuvwx", id="dirty")
        state = {"messages": [clean, dirty]}

        result = mw.before_model(state, runtime=None)

        self.assertIsNotNone(result)
        self.assertIs(result["messages"][0], clean)
        self.assertIsNot(result["messages"][1], dirty)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwx", result["messages"][1].content)


class NameFieldPreservedTests(SimpleTestCase):
    def test_name_is_preserved_after_masking(self):
        mw = SensitiveInputMaskMiddleware()
        original = HumanMessage(content="api_key: sk-abcdefghijklmnopqrstuvwx", name="사용자A")
        state = {"messages": [original]}

        result = mw.before_model(state, runtime=None)

        self.assertEqual(result["messages"][0].name, "사용자A")
