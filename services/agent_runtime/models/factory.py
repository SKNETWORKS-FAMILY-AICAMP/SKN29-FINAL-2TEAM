"""모델 이름과 팀 설정을 LangChain 모델 객체로 변환한다."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Literal

from django.conf import settings
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from backend.db.agent_platform import CustomModelRepository
from services.agent_runtime.exceptions import ModelUnavailableError

logger = logging.getLogger(__name__)

Provider = Literal["anthropic", "openai", "openai_compatible"]


@dataclass(frozen=True)
class ResolvedModelConfig:
    """모델 provider, 접속 정보, 추론 설정을 담는다."""

    provider: Provider
    model_id: str
    api_key: str
    base_url: str | None
    reasoning_effort: str


def resolved_endpoint_hash(resolved: "ResolvedModelConfig") -> str | None:
    """`agent_run.resolved_endpoint_hash`(2026-08-19, §4순위 Run Snapshot,
    정본: `2026-08-19_01_실행_안정성_설계.md` §1)에 남길 값.

    `base_url` 원문을 그대로 실행 로그에 남기면 팀이 등록한 사내망 주소가
    로그에 그대로 노출된다 — sha256 해시만 남기면 "그때와 지금이 같은
    엔드포인트로 나갔는지" 비교하는 용도로는 충분하고 원문은 복원할 수
    없다. `base_url`이 없으면(anthropic/openai 기본 엔드포인트,
    팀 커스텀 엔드포인트가 아닌 경우) `None` — 비교할 대상 자체가 없다.
    """
    if not resolved.base_url:
        return None
    return hashlib.sha256(resolved.base_url.encode("utf-8")).hexdigest()


class ModelConfigResolver:
    """모델 이름을 provider와 접속 설정으로 변환한다.

    우선순위: 팀 커스텀 엔드포인트 → "claude-" 접두사면 Anthropic → 그 외 OpenAI.
    """

    def resolve(self, *, model: str, reasoning_effort: str, team_id: str | None) -> ResolvedModelConfig:
        # `agent_versions.model`은 DB에 NOT NULL이 아니다(DB/schema.sql) — 저장
        # API(`AgentVersionPublishSerializer.model`)도 `allow_null=True`로 NULL을
        # 그대로 받아 준다. 여기서 안 막으면 아래 `model.startswith("claude-")`가
        # `AttributeError: 'NoneType' object has no attribute 'startswith'`로
        # 깨져서, 사용자에게는 원인을 알 수 없는 크래시로만 보인다(2026-08-19 —
        # 코드에 이미 자체 인지되어 있던 문제, `provision_default_chat_agent()`
        # docstring 참고). 도메인 오류로 먼저 잡아 이유를 말한다.
        if not model:
            raise ModelUnavailableError("이 에이전트에는 아직 모델이 설정되지 않았습니다.")
        custom = self._team_endpoint(team_id, model)
        if custom is not None:
            api_key = str(custom.get("api_key") or "").strip()
            if not api_key:
                raise ModelUnavailableError(
                    f"팀 커스텀 모델 '{model}'에 등록된 API 키가 없습니다."
                )
            return ResolvedModelConfig(
                provider="openai_compatible",
                model_id=model,
                api_key=api_key,
                base_url=str(custom.get("base_url") or "").strip() or None,
                reasoning_effort=reasoning_effort,
            )

        if model.startswith("claude-"):
            api_key = str(getattr(settings, "ANTHROPIC_API_KEY", "") or "").strip()
            if not api_key:
                raise ModelUnavailableError("ANTHROPIC_API_KEY가 설정되어 있지 않습니다.")
            return ResolvedModelConfig(
                provider="anthropic",
                model_id=model,
                api_key=api_key,
                base_url=None,
                reasoning_effort=reasoning_effort,
            )

        api_key = str(getattr(settings, "OPENAI_API_KEY", "") or "").strip()
        if not api_key:
            raise ModelUnavailableError("OPENAI_API_KEY가 설정되어 있지 않습니다.")
        return ResolvedModelConfig(
            provider="openai",
            model_id=model,
            api_key=api_key,
            base_url=None,
            reasoning_effort=reasoning_effort,
        )

    @staticmethod
    def _team_endpoint(team_id: str | None, model: str | None) -> dict[str, object] | None:
        """팀에 등록된 커스텀 엔드포인트를 조회한다."""
        if not team_id or not model:
            return None
        try:
            return CustomModelRepository.for_model(team_id, model)
        except Exception:  # noqa: BLE001 - 조회 실패로 에이전트 실행 전체를 막지 않는다
            logger.exception("커스텀 모델 API를 읽지 못했습니다: team=%s", team_id)
            return None


class ModelFactory:
    """해석된 설정으로 provider별 `BaseChatModel`을 생성한다."""

    def create(self, resolved: ResolvedModelConfig) -> BaseChatModel:
        if resolved.provider == "anthropic":
            return self._create_anthropic(resolved)
        if resolved.provider == "openai":
            return self._create_openai(resolved)
        if resolved.provider == "openai_compatible":
            return self._create_openai_compatible(resolved)
        raise ModelUnavailableError(f"알 수 없는 provider입니다: {resolved.provider}")

    @staticmethod
    def _create_anthropic(resolved: ResolvedModelConfig) -> BaseChatModel:
        kwargs: dict[str, object] = {
            "model": resolved.model_id,
            "anthropic_api_key": resolved.api_key,
        }
        if resolved.reasoning_effort:
            kwargs["output_config"] = {"effort": resolved.reasoning_effort}
        return ChatAnthropic(**kwargs)

    @staticmethod
    def _create_openai(resolved: ResolvedModelConfig) -> BaseChatModel:
        kwargs: dict[str, object] = {
            "model": resolved.model_id,
            "openai_api_key": resolved.api_key,
            "use_responses_api": True,
        }
        if resolved.reasoning_effort:
            # `reasoning_effort=` 단독으로 넘기면 langchain-openai가 이걸
            # `reasoning={"effort": ...}`로만 바꿔 보낸다(`summary` 없음 —
            # 패키지 소스 `_construct_responses_api_payload` 확인,
            # 2026-08-18). 그러면 OpenAI가 reasoning 블록을 **빈 summary로만**
            # 돌려줘서(`services/agent_runtime/events.py`의 `_extract_reasoning`이
            # 읽을 게 없다), "생각 과정" 카드가 항상 비어 있게 된다. `summary`를
            # 직접 요청해야 실제 텍스트가 온다(패키지 docstring 예시 그대로).
            kwargs["reasoning"] = {"effort": resolved.reasoning_effort, "summary": "auto"}
        return ChatOpenAI(**kwargs)

    @staticmethod
    def _create_openai_compatible(resolved: ResolvedModelConfig) -> BaseChatModel:
        # OpenAI 호환 엔드포인트는 reasoning_effort 지원을 보장하지 않는다.
        return ChatOpenAI(
            model=resolved.model_id,
            openai_api_key=resolved.api_key,
            openai_api_base=resolved.base_url,
            use_responses_api=False,
        )
