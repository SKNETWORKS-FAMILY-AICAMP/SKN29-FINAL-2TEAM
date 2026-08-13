"""모델명·Reasoning 설정을 이용해 실제 모델 클라이언트를 생성한다.

⚠ 미구현 — 그리고 스텁으로 남겨두는 이유가 단순 "아직 안 짬"이 아니라 미정 사항이
있어서다.

이 프로젝트는 이미 `services/harness/runner._default_model`에 자체 라우팅이
있다: `claude-`로 시작하면 Anthropic, 팀이 등록한 커스텀 이름이면 그 팀의
base_url(OpenAI 호환), 나머지는 OpenAI Responses API(`작업목록.md` "모델을
화면에서 고른다" 절 참조). deepagents는 기본으로 langchain-anthropic·
langchain-google-genai 네이티브 통합을 쓴다(requirements/base.txt 주석 참고).

**정할 것**: 이 팀의 커스텀 모델(사내 요청 → 운영자가 /ops/models로 등록,
OpenAI 호환 base_url)을 deepagents 쪽에서도 langchain-openai의 ChatOpenAI에
base_url을 얹어 통일할지, 아니면 provider별 네이티브 langchain 통합을 쓸지 —
이건 §15 스트리밍 스파이크 때 langchain-openai를 추가할지와 함께 결정한다
(지금은 추가 안 했다).
"""

from __future__ import annotations

from typing import Any

from services.agent_runtime.exceptions import ModelUnavailableError


class ModelFactory:
    def create(self, *, model: str, reasoning_effort: str) -> Any:
        raise NotImplementedError(
            "라우팅 정책(claude-* / 팀 커스텀 base_url / OpenAI) 결정 후 구현. "
            "결정 근거는 이 파일 상단 docstring과 services/harness/runner._default_model."
        )
