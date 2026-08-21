"""공급자 공통 계약과 갈림길.

**결과를 두 가지로만 표현한다** — 막을 것인가(`blocked`)와 왜(`reason`·`detail`).
공급자마다 판정 형식이 다르지만(Azure 는 심각도 0~6, Bedrock 은 개입 여부,
OpenAI 는 tripwire) 부르는 쪽이 알아야 할 것은 그 둘뿐이다.

**`detail` 에 원문을 담지 않는다.** 그대로 `guardrail_event` 로 들어가고, 가려진
값이 기록에 남으면 가드레일을 두는 의미가 없다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ProviderError(Exception):
    """공급자를 부르지 못했다(주소·키·네트워크). 판정 실패와 구분한다."""


@dataclass(frozen=True)
class GuardrailVerdict:
    """검사 한 번의 결과."""

    blocked: bool
    #: 무엇에 걸렸는지 — 카테고리·점수처럼 기록에 남길 값만.
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VerifyResult:
    """「연결 확인」 결과. 실패 사유는 화면이 그대로 보여준다."""

    ok: bool
    detail: str | None = None


def verify(*, kind: str, config: dict[str, Any], credential: dict[str, Any] | None) -> VerifyResult:
    """저장하지 않고 붙는지만 본다(MCP 의 「연결 확인」과 같은 자리).

    **무해한 문장 하나를 실제로 보낸다.** 자격증명만 형식 검사하면 「등록은 됐는데
    부를 때 401」이 되고, 그 팀은 운영자가 붙여 줬으니 되는 줄 안다.
    """

    provider = _provider(kind)
    try:
        provider.check(text=_PROBE_TEXT, config=config, credential=credential)
    except ProviderError as exc:
        return VerifyResult(ok=False, detail=str(exc))
    return VerifyResult(ok=True)


def check(
    *, kind: str, text: str, config: dict[str, Any], credential: dict[str, Any] | None
) -> GuardrailVerdict:
    """등록된 공급자로 텍스트 한 건을 검사한다."""

    return _provider(kind).check(text=text, config=config, credential=credential)


#: 「연결 확인」이 보내는 문장. 어느 공급자에서도 걸리지 않을 평범한 업무 문장이라야
#: **붙었는지**와 **걸렸는지**가 안 섞인다.
_PROBE_TEXT = "안녕하세요. 연결 확인용 문장입니다."


def _provider(kind: str):
    # 지연 임포트다 — Bedrock 은 boto3, OpenAI Guardrails 는 무거운 패키지를 끌어온다.
    # 등록만 하고 안 쓰는 공급자 때문에 기동이 느려지지 않게 부를 때 읽는다.
    if kind == "AZURE_CONTENT_SAFETY":
        from . import azure

        return azure
    if kind == "BEDROCK_GUARDRAILS":
        from . import bedrock

        return bedrock
    if kind == "OPENAI_GUARDRAILS":
        from . import openai_guardrails

        return openai_guardrails
    raise ProviderError(f"알 수 없는 가드레일 종류입니다: {kind}")
