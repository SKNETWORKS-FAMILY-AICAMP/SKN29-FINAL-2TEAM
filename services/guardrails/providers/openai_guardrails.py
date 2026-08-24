"""OpenAI Guardrails — 설치형 라이브러리(`openai-guardrails`).

**셋 중 유일하게 원격 엔드포인트가 아니다.** 고객이 등록하는 것은 주소가 아니라
guardrails.openai.com 위저드가 뽑아 주는 **설정 JSON** 과 OpenAI 키다. 검사는 우리
서버에서 그 라이브러리가 돌리고, 그 안에서 다시 고객 키로 OpenAI 를 부른다.

우리가 쓰는 것은 드롭인 클라이언트(`GuardrailsAsyncOpenAI`)가 **아니라** standalone
경로다 — 우리 모델 호출은 langchain 3사 경유라 클라이언트를 갈아끼울 수 없다:

    bundles = load_pipeline_bundles(<설정 dict>)   # pre_flight / input / output
    guardrails = instantiate_guardrails(bundles.<stage>)
    results = await run_guardrails(ctx, text, "text/plain", guardrails,
                                   suppress_tripwire=True)

`ctx` 는 `guardrail_llm` 하나짜리다(2026-08-20 에 `runtime._get_default_ctx` 로
확인). 기본 ctx 는 환경변수 키로 클라이언트를 만들기 때문에 쓰지 않는다 —
**등록한 고객 키로** 우리가 직접 만들어 넘긴다.

**`output` 단계는 돌리지 않는다.** 우리 배선이 입력 측뿐이라, 돌려 봐야 검사할
모델 응답이 없다.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any

from .base import GuardrailVerdict, ProviderError

#: 입력 한 건에 적용할 단계. 위저드는 Moderation 을 `pre_flight`, Jailbreak 을
#: `input` 에 넣으므로 둘 다 돌려야 고른 대로 동작한다.
#: 호출 timeout(초). 사용자 발화를 붙들고 있는 자리라 짧게 잡는다
#: (azure·bedrock 과 같은 값).
TIMEOUT_SECONDS = 10

INPUT_STAGES = ("pre_flight", "input")


def check(
    *, text: str, config: dict[str, Any], credential: dict[str, Any] | None
) -> GuardrailVerdict:
    pipeline = _pipeline(config)
    api_key = str((credential or {}).get("api_key") or "").strip()
    if not api_key:
        raise ProviderError("OpenAI 키가 없습니다.")

    try:
        from guardrails import instantiate_guardrails, load_pipeline_bundles, run_guardrails
        from openai import AsyncOpenAI
    except ImportError as exc:  # pragma: no cover - 배포에는 항상 있다
        raise ProviderError("이 서버에 openai-guardrails 가 설치돼 있지 않습니다.") from exc

    try:
        bundles = load_pipeline_bundles(pipeline)
    except Exception as exc:  # noqa: BLE001 - 라이브러리가 자체 예외를 던진다
        raise ProviderError(f"설정 JSON 을 읽지 못했습니다: {exc.__class__.__name__}") from exc

    @dataclass
    class _Ctx:
        guardrail_llm: Any

    # **timeout 을 반드시 준다.** openai SDK 기본값은 600초에 재시도 2회라,
    # 그대로 두면 OpenAI 가 흔들릴 때 사용자 발화가 최악 30분까지 붙들린다 —
    # 「호출이 안 되는」 경우보다 「느리게 되는」 경우가 더 위험하다.
    # Azure·Bedrock 과 같은 값으로 맞춘다.
    ctx = _Ctx(guardrail_llm=AsyncOpenAI(api_key=api_key, timeout=TIMEOUT_SECONDS, max_retries=0))

    async def _run() -> list[Any]:
        collected: list[Any] = []
        try:
            for stage in INPUT_STAGES:
                bundle = getattr(bundles, stage, None)
                if bundle is None or not bundle.guardrails:
                    continue
                configured = instantiate_guardrails(bundle)
                # `suppress_tripwire=True` — 걸렸다고 예외로 끊지 않고 결과를 다 받는다.
                # 막을지 말지는 우리가 정한다(부르는 쪽이 기록도 남겨야 한다).
                collected.extend(
                    await run_guardrails(
                        ctx,
                        text,
                        "text/plain",
                        configured,
                        suppress_tripwire=True,
                        # **기본값 False 를 그대로 쓰면 안 된다**(2026-08-20 실측).
                        # 키가 틀려 호출이 실패해도 예외 없이 「걸린 것 없음」으로
                        # 돌아와서, 「연결 확인」이 가짜 키를 **연결됨으로 판정했다.**
                        # 우리는 못 부른 것과 통과한 것을 반드시 구분해야 한다 —
                        # 안 되는 것을 등록해 두면 그 팀의 대화가 조용히 검사를
                        # 건너뛴다.
                        raise_guardrail_errors=True,
                    )
                )
        finally:
            # **닫지 않으면 `RuntimeError: Event loop is closed` 가 로그에 쌓인다**
            # (2026-08-20 실측). `asyncio.run()` 이 루프를 닫은 뒤에 클라이언트가
            # 정리되면서 이미 닫힌 루프를 건드리기 때문이다.
            await ctx.guardrail_llm.close()
        return collected

    try:
        results = asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001 - 네트워크·설정·모델 어느 쪽이든 못 부른 것이다
        raise ProviderError(_reason(exc)) from exc

    for result in results:
        if getattr(result, "tripwire_triggered", False):
            info = getattr(result, "info", None) or {}
            return GuardrailVerdict(
                blocked=True,
                # 무엇에 걸렸는지 이름만 남긴다 — `info` 를 통째로 담으면 원문
                # 조각이 기록으로 샌다.
                detail={"guardrail": info.get("guardrail_name") if isinstance(info, dict) else None},
            )
    return GuardrailVerdict(blocked=False)


def _pipeline(config: dict[str, Any]) -> dict[str, Any]:
    """등록된 설정 JSON. 문자열로 저장돼 있으므로 여기서 푼다."""

    raw = (config or {}).get("pipeline")
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        raise ProviderError("설정 JSON 이 없습니다.")
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise ProviderError("설정 JSON 형식이 올바르지 않습니다.") from exc
    if not isinstance(parsed, dict):
        raise ProviderError("설정 JSON 형식이 올바르지 않습니다.")
    return parsed


def _reason(exc: BaseException) -> str:
    """운영자가 고칠 수 있는 말로 바꾼다.

    `run_guardrails` 는 여러 검사를 동시에 돌려 실패를 `ExceptionGroup` 으로 묶고,
    그 안은 평범한 `Exception` 이라 클래스 이름만으로는 아무것도 알 수 없다
    (2026-08-20 실측: 화면에 「ExceptionGroup」만 떴다).

    **예외 문자열을 그대로 쓰지 않는다.** OpenAI 가 가려서 주긴 하지만 그 안에 키
    조각이 들어 있다(`Incorrect API key provided: sk-not-a*****-key`) — 상태 코드만
    뽑는다.
    """

    text = str(_first_cause(exc))
    match = re.search(r"Error code:\s*(\d{3})", text)
    if match is None:
        return f"검사하지 못했습니다: {_first_cause(exc).__class__.__name__}"

    code = match.group(1)
    if code == "401":
        return "키가 올바르지 않습니다."
    if code == "429":
        return "호출 한도에 걸렸습니다. 잠시 뒤 다시 시도해 주세요."
    return f"응답이 정상이 아닙니다({code})."


def _first_cause(exc: BaseException) -> BaseException:
    """중첩된 `ExceptionGroup` 을 풀어 처음 만나는 실제 예외를 준다."""

    seen = exc
    while True:
        nested = getattr(seen, "exceptions", None)
        if not nested:
            return seen
        seen = nested[0]
