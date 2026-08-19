"""models/factory.py(ModelConfigResolver, ModelFactory) 단위 테스트.

정본: docs/작업기록/Deep_Agents/2026-08-13_04_작업자B_실행코어_세부계획.md §6-3

DB는 안 띄운다 — `CustomModelRepository.for_model`을 mock한다(tests/test_harness.py의
RegistryTests와 같은 패턴). 실제 Anthropic/OpenAI API는 호출하지 않는다 —
`ModelFactory.create()`가 반환하는 LangChain 클라이언트 객체가 올바른 kwargs로
만들어졌는지만 본다(생성자는 네트워크 호출을 하지 않는다).
"""

from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from services.agent_runtime.exceptions import ModelUnavailableError
from services.agent_runtime.models.factory import (
    ModelConfigResolver,
    ModelFactory,
    ResolvedModelConfig,
    resolved_endpoint_hash,
)

FACTORY_MODULE = "services.agent_runtime.models.factory"


@override_settings(ANTHROPIC_API_KEY="test-anthropic-key", OPENAI_API_KEY="test-openai-key")
class ModelConfigResolverTests(SimpleTestCase):
    def setUp(self):
        self.resolver = ModelConfigResolver()

    @patch(f"{FACTORY_MODULE}.CustomModelRepository.for_model")
    def test_prefers_team_custom_endpoint_when_registered(self, mock_for_model):
        mock_for_model.return_value = {
            "api_key": "custom-key",
            "base_url": "https://custom.example.com/v1",
            "model": "claude-x",
        }

        resolved = self.resolver.resolve(model="claude-x", reasoning_effort="low", team_id="TM1")

        self.assertEqual(resolved.provider, "openai_compatible")
        self.assertEqual(resolved.api_key, "custom-key")
        self.assertEqual(resolved.base_url, "https://custom.example.com/v1")

    @patch(f"{FACTORY_MODULE}.CustomModelRepository.for_model", return_value=None)
    def test_routes_claude_prefixed_models_to_anthropic(self, _mock_for_model):
        resolved = self.resolver.resolve(model="claude-sonnet-5", reasoning_effort="medium", team_id="TM1")

        self.assertEqual(resolved.provider, "anthropic")
        self.assertEqual(resolved.api_key, "test-anthropic-key")

    @patch(f"{FACTORY_MODULE}.CustomModelRepository.for_model", return_value=None)
    def test_routes_other_models_to_openai_by_default(self, _mock_for_model):
        resolved = self.resolver.resolve(model="gpt-5.6-luna", reasoning_effort="low", team_id="TM1")

        self.assertEqual(resolved.provider, "openai")
        self.assertEqual(resolved.api_key, "test-openai-key")

    @patch(f"{FACTORY_MODULE}.CustomModelRepository.for_model")
    def test_skips_custom_lookup_when_team_id_missing(self, mock_for_model):
        resolved = self.resolver.resolve(model="claude-x", reasoning_effort="low", team_id=None)

        mock_for_model.assert_not_called()
        self.assertEqual(resolved.provider, "anthropic")

    @patch(f"{FACTORY_MODULE}.CustomModelRepository.for_model", return_value=None)
    @override_settings(ANTHROPIC_API_KEY="")
    def test_raises_when_anthropic_api_key_missing(self, _mock_for_model):
        with self.assertRaises(ModelUnavailableError):
            self.resolver.resolve(model="claude-sonnet-5", reasoning_effort="low", team_id=None)

    @patch(f"{FACTORY_MODULE}.CustomModelRepository.for_model", return_value=None)
    @override_settings(OPENAI_API_KEY="")
    def test_raises_when_openai_api_key_missing(self, _mock_for_model):
        with self.assertRaises(ModelUnavailableError):
            self.resolver.resolve(model="gpt-5.6-luna", reasoning_effort="low", team_id=None)

    @patch(f"{FACTORY_MODULE}.CustomModelRepository.for_model", side_effect=RuntimeError("DB 다운"))
    def test_falls_back_silently_when_custom_lookup_fails(self, _mock_for_model):
        """커스텀 엔드포인트 조회 실패가 에이전트 실행 전체를 죽이면 안 된다."""

        resolved = self.resolver.resolve(model="claude-sonnet-5", reasoning_effort="low", team_id="TM1")

        self.assertEqual(resolved.provider, "anthropic")

    @patch(f"{FACTORY_MODULE}.CustomModelRepository.for_model")
    def test_raises_when_custom_endpoint_has_no_api_key(self, mock_for_model):
        mock_for_model.return_value = {"api_key": "", "base_url": "https://x", "model": "claude-x"}

        with self.assertRaises(ModelUnavailableError):
            self.resolver.resolve(model="claude-x", reasoning_effort="low", team_id="TM1")


class ModelFactoryTests(SimpleTestCase):
    def setUp(self):
        self.factory = ModelFactory()

    def test_builds_chat_anthropic_with_effort_output_config(self):
        resolved = ResolvedModelConfig(
            provider="anthropic", model_id="claude-sonnet-5", api_key="k", base_url=None, reasoning_effort="low"
        )

        model = self.factory.create(resolved)

        self.assertIsInstance(model, ChatAnthropic)
        self.assertEqual(model.output_config, {"effort": "low"})

    def test_builds_chat_anthropic_without_output_config_when_no_reasoning_effort(self):
        resolved = ResolvedModelConfig(
            provider="anthropic", model_id="claude-sonnet-5", api_key="k", base_url=None, reasoning_effort=""
        )

        model = self.factory.create(resolved)

        self.assertIsNone(model.output_config)

    def test_builds_chat_openai_with_responses_api_and_reasoning_effort(self):
        """`reasoning_effort=`이 아니라 `reasoning={"effort": ..., "summary":
        "auto"}`로 넘긴다(2026-08-18) — `reasoning_effort=` 단독으로는
        langchain-openai가 `summary`를 안 실어 보내 API가 reasoning 블록을
        빈 summary로만 돌려주고, 그러면 「생각 과정」 카드(services/agent_runtime
        /events.py의 `_extract_reasoning`)가 보여줄 텍스트가 없다."""
        resolved = ResolvedModelConfig(
            provider="openai", model_id="gpt-5.6-luna", api_key="k", base_url=None, reasoning_effort="low"
        )

        model = self.factory.create(resolved)

        self.assertIsInstance(model, ChatOpenAI)
        self.assertTrue(model.use_responses_api)
        self.assertEqual(model.reasoning, {"effort": "low", "summary": "auto"})

    def test_builds_chat_openai_compatible_without_reasoning_effort(self):
        """호환 엔드포인트마다 reasoning 파라미터 지원이 달라 400 위험이 있다(레거시 실측) —
        이 경로는 reasoning_effort를 의도적으로 보내지 않는다."""

        resolved = ResolvedModelConfig(
            provider="openai_compatible",
            model_id="claude-x",
            api_key="k",
            base_url="https://custom.example.com/v1",
            reasoning_effort="low",
        )

        model = self.factory.create(resolved)

        self.assertIsInstance(model, ChatOpenAI)
        self.assertFalse(model.use_responses_api)
        self.assertIsNone(model.reasoning_effort)
        self.assertEqual(model.openai_api_base, "https://custom.example.com/v1")

    def test_raises_for_unknown_provider(self):
        resolved = ResolvedModelConfig(
            provider="does-not-exist",  # type: ignore[arg-type]
            model_id="x",
            api_key="k",
            base_url=None,
            reasoning_effort="",
        )

        with self.assertRaises(ModelUnavailableError):
            self.factory.create(resolved)


class ResolvedEndpointHashTests(SimpleTestCase):
    """2026-08-19, §4순위(Run Snapshot) — `agent_run.resolved_endpoint_hash`에
    남길 값. base_url 원문이 로그에 그대로 남지 않는지가 핵심이다."""

    def test_no_base_url_hashes_to_none(self):
        """anthropic/openai 기본 엔드포인트(팀 커스텀 아님)는 비교할 대상
        자체가 없다."""
        resolved = ResolvedModelConfig(
            provider="anthropic", model_id="claude-sonnet-5", api_key="k", base_url=None, reasoning_effort="low"
        )

        self.assertIsNone(resolved_endpoint_hash(resolved))

    def test_base_url_is_hashed_not_stored_verbatim(self):
        resolved = ResolvedModelConfig(
            provider="openai_compatible",
            model_id="claude-x",
            api_key="k",
            base_url="https://internal.company.example.com/v1",
            reasoning_effort="low",
        )

        result = resolved_endpoint_hash(resolved)

        self.assertIsNotNone(result)
        self.assertNotIn("internal.company.example.com", result)

    def test_same_base_url_hashes_identically(self):
        """"그때와 지금이 같은 엔드포인트인지" 비교하는 용도라 — 결정적이어야
        한다."""
        a = ResolvedModelConfig(
            provider="openai_compatible", model_id="m", api_key="k", base_url="https://x.example.com/v1", reasoning_effort=""
        )
        b = ResolvedModelConfig(
            provider="openai_compatible", model_id="m", api_key="k2", base_url="https://x.example.com/v1", reasoning_effort="low"
        )

        self.assertEqual(resolved_endpoint_hash(a), resolved_endpoint_hash(b))

    def test_different_base_url_hashes_differently(self):
        a = ResolvedModelConfig(
            provider="openai_compatible", model_id="m", api_key="k", base_url="https://a.example.com/v1", reasoning_effort=""
        )
        b = ResolvedModelConfig(
            provider="openai_compatible", model_id="m", api_key="k", base_url="https://b.example.com/v1", reasoning_effort=""
        )

        self.assertNotEqual(resolved_endpoint_hash(a), resolved_endpoint_hash(b))
