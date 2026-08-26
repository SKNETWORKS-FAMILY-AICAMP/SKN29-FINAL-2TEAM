"""model_key 매칭이 실제로 tool 제외를 적용하는지 확인하는 통합 테스트.

정본: docs/설계 및 구현/3_중간발표 이후/작업기록/Deep_Agents/2026-08-13_04_작업자B_실행코어_세부계획.md §9.3

실제 ChatAnthropic/ChatOpenAI 인스턴스로 provider 문자열을 확인하고(네트워크 호출
없음, 생성자 단계라 안전), 그 provider로 harness profile을 등록했을 때 deepagents가
실제로 excluded_tools를 모델에 보내는 tool 목록에서 제거하는지까지 오프라인으로
검증한다. 후자는 실제 API 키가 필요 없는 스크립트 모델로 확인한다 — `_get_ls_params`만
실제 provider 값을 흉내 내면 deepagents 내부 profile 조회 코드가 실제 모델과 똑같은
경로를 탄다(get_model_provider가 이 메서드만 본다, deepagents 소스로 확인).
"""

from __future__ import annotations

from django.conf import settings
from django.test import SimpleTestCase, override_settings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool, tool
from pydantic import Field

from deepagents import GeneralPurposeSubagentProfile, HarnessProfile, create_deep_agent
from deepagents._models import get_model_provider

from services.agent_runtime.compat import register_default_harness_profile
from services.agent_runtime.models.factory import ModelFactory, ResolvedModelConfig

# 정책 기본값(`DEFAULT_EXCLUDED_BUILTIN_TOOLS`)은 이제 비어 있다(2026-08-26) —
# 여기서 검증하려는 건 "제외 목록이 실제로 필터링되는가"이지 그 목록이 뭔지가
# 아니라서, 실제 존재하는 builtin tool 이름으로 이 테스트만의 값을 쓴다.
_TEST_EXCLUDED_TOOLS: frozenset[str] = frozenset({"write_file"})


class _ProviderAwareScriptedModel(BaseChatModel):
    """`_get_ls_params`가 실제 provider 값을 그대로 돌려주는 스크립트 모델.

    실제 API 호출 없이 `bind_tools()`에 넘어온 tool 이름만 기록한다.
    """

    responses: list = Field(default_factory=list)
    call_count: int = 0
    bind_calls_log: list = Field(default_factory=list)
    provider: str = "anthropic"

    model_config = {"arbitrary_types_allowed": True}

    def _get_ls_params(self, **kwargs):
        return {"ls_provider": self.provider, "ls_model_name": "fake-model"}

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        names = []
        for t in tools:
            if isinstance(t, BaseTool):
                names.append(t.name)
            elif isinstance(t, dict):
                names.append(t.get("name") or (t.get("function") or {}).get("name"))
            else:
                names.append(getattr(t, "name", None))
        self.bind_calls_log.append(names)
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        idx = min(self.call_count, len(self.responses) - 1)
        response = self.responses[idx]
        self.call_count += 1
        return ChatResult(generations=[ChatGeneration(message=response)])

    @property
    def _llm_type(self):
        return "provider-aware-scripted-fake"


@tool
def _document_search(query: str) -> str:
    """문서를 검색한다."""
    return "ok"


@override_settings(ANTHROPIC_API_KEY="test-anthropic-key", OPENAI_API_KEY="test-openai-key")
class RealModelProviderResolutionTests(SimpleTestCase):
    """`ModelFactory`가 만든 실제 모델 인스턴스의 provider가 우리가 등록에 쓰는 값과 일치하는가."""

    def setUp(self):
        self.factory = ModelFactory()

    def test_anthropic_model_resolves_to_anthropic_provider(self):
        resolved = ResolvedModelConfig(
            provider="anthropic", model_id="claude-sonnet-5", api_key="k", base_url=None, reasoning_effort=""
        )
        model = self.factory.create(resolved)

        self.assertEqual(get_model_provider(model), "anthropic")

    def test_openai_model_resolves_to_openai_provider(self):
        resolved = ResolvedModelConfig(
            provider="openai", model_id="gpt-5", api_key="k", base_url=None, reasoning_effort=""
        )
        model = self.factory.create(resolved)

        self.assertEqual(get_model_provider(model), "openai")

    def test_openai_compatible_model_also_resolves_to_bare_openai_provider(self):
        """`openai_compatible`이라는 별도 provider 키로 harness profile을 등록해도
        deepagents는 절대 그 키로 조회하지 않는다 — ChatOpenAI 인스턴스인 이상
        `get_model_provider()`는 base_url과 무관하게 항상 "openai"를 돌려준다."""

        resolved = ResolvedModelConfig(
            provider="openai_compatible",
            model_id="team-model",
            api_key="k",
            base_url="https://team-endpoint.example.com",
            reasoning_effort="",
        )
        model = self.factory.create(resolved)

        self.assertEqual(get_model_provider(model), "openai")


class ExcludedToolsActuallyFilteredTests(SimpleTestCase):
    """provider로 등록한 harness profile이 실제로 모델에 보내는 tool 목록에서 제외 도구를 뺴는가."""

    def test_excluded_builtin_tools_never_reach_model_when_provider_matches(self):
        register_default_harness_profile(
            model_key="anthropic", excluded_tools=_TEST_EXCLUDED_TOOLS
        )
        model = _ProviderAwareScriptedModel(responses=[AIMessage(content="ok")], provider="anthropic")

        graph = create_deep_agent(
            model=model, system_prompt="test", tools=[_document_search], subagents=[]
        )
        graph.invoke({"messages": [{"role": "user", "content": "hi"}]})

        bound_names = {n for call in model.bind_calls_log for n in call if n}
        self.assertFalse(bound_names & _TEST_EXCLUDED_TOOLS)
        self.assertIn("_document_search", bound_names)

    def test_mismatched_provider_key_does_not_apply_exclusion(self):
        """model_key 오타·불일치가 왜 "조용한 실패"인지 재현 — provider가 다르면
        excluded_tools는 그냥 조용히 무시된다(예외 없음)."""

        register_default_harness_profile(
            model_key="anthropic", excluded_tools=_TEST_EXCLUDED_TOOLS
        )
        model = _ProviderAwareScriptedModel(
            responses=[AIMessage(content="ok")], provider="some-other-provider"
        )

        graph = create_deep_agent(model=model, system_prompt="test", tools=[], subagents=[])
        graph.invoke({"messages": [{"role": "user", "content": "hi"}]})

        bound_names = {n for call in model.bind_calls_log for n in call if n}
        self.assertTrue(bound_names & _TEST_EXCLUDED_TOOLS)
