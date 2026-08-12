"""빌더 에이전트 — BuilderInput 한 건을 검토한다.

**판정과 보정을 분리한 두 번의 호출로 나눈다.** 먼저 description/behavior가
명확한지·선택한 도구가 behavior와 맞는지만 판정하고(`overall`), 실제로 고칠 게
있는 `warn`일 때만 behavior를 instruction으로 다듬는 두 번째 호출을 한다.
`pass`는 이미 다듬을 게 없으므로 원문을 그대로 돌려주고, `reject`는 애초에
다듬을 실질 내용이 없으므로 빈 문자열을 돌려준다 — 두 경우 다 보정 호출을
아예 하지 않는다. 판정 하나에 항상 재작성 문장이 따라붙던 예전 방식은 이미
좋은 지시문에도 매번 "더 손볼 게 있다"는 인상을 줬다(2026-08-12 실측).

**pass/warn은 저장을 막지 않는다.** 단, reject는 다르다 — description/behavior가
사실상 비어 있거나 위임 표현뿐이라 다듬어서 쓸 지시문이 나오지 않는 수준이면
reject다. 호출하는 화면이 다음 단계 진행을 막는 데 쓴다.
"""

from __future__ import annotations

from typing import Any, Literal

from django.conf import settings
from openai import OpenAI
from pydantic import BaseModel, Field

from services.document_pipeline.errors import PipelineConfigurationError
from services.harness.scaffold import COMMON_SCAFFOLD

# 빌더가 생성하는 에이전트는 항상 max_iterations=6 고정값을 쓴다
# (`apps/agents/serializers.py::AgentWriteSerializer` 기본값과 같다).
_SCAFFOLD_TEXT = COMMON_SCAFFOLD.format(max_iterations=6)

#: 검토·보정에 쓰는 모델. 짧은 판단이라 싼 것으로 충분하다.
#:
#: 예전에는 `settings.OPENAI_PLAN_MODEL` 이었는데, `.env` 로 모델을 고정하던 것을
#: 걷어내면서 그 설정이 없어졌다(2026-08-12). 여기서 정할 값은 **사용자가 고르는
#: 값이 아니라** 검토 단계의 고정 비용이라, 각 모듈이 자기 상수로 들고 있는다 —
#: `task_extraction.PLAN_MODEL`·`harness.naming.TITLE_MODEL` 과 같은 규칙이다.
PLAN_MODEL = "gpt-5.6-luna"


class DescriptionCheck(BaseModel):
    note: str | None = None


class InstructionCheck(BaseModel):
    note: str | None = None


class ToolMatchCheck(BaseModel):
    missing_tools: list[str] = Field(default_factory=list)
    unused_tools: list[str] = Field(default_factory=list)


class BuilderJudgment(BaseModel):
    """1차 호출 — 판정만 한다. 문장을 다듬는 일은 하지 않는다."""

    description_check: DescriptionCheck
    instruction_check: InstructionCheck
    tool_match_check: ToolMatchCheck
    overall: Literal["pass", "warn", "reject"]
    reject_reason: str | None = None


class RefinedInstruction(BaseModel):
    """2차 호출(`warn`일 때만) — 판정에서 짚인 문제를 반영해 behavior를 다듬는다."""

    refined_instruction: str


class BuilderCheckResult(BaseModel):
    refined_instruction: str
    description_check: DescriptionCheck
    instruction_check: InstructionCheck
    tool_match_check: ToolMatchCheck
    overall: Literal["pass", "warn", "reject"]
    reject_reason: str | None = None


class InstructionRecheckResult(BaseModel):
    """지시문 재검증 결과. `description_check`가 없다 — 설명은 다시 안 본다."""

    instruction_check: InstructionCheck
    tool_match_check: ToolMatchCheck
    overall: Literal["pass", "warn", "reject"]
    reject_reason: str | None = None


_JUDGE_SYSTEM_PROMPT = (
    "에이전트 빌더 검토 담당이다. 사용자가 자연어로 적은 행동 지시(behavior)와 설명"
    "(description), 선택한 도구가 서로 맞는지 **판정만** 한다. 문장을 다듬는 일은 여기서 "
    "하지 않는다 — 그건 warn일 때만 별도로 부르는 다른 담당의 몫이다.\n\n"
    "아래는 이 팀의 모든 에이전트에 이미 공통으로 적용되는 스캐폴드 문구다 — 개별 "
    "behavior가 이 내용을 반복하거나 이 내용과 모순되는지 판단할 때 참고하라:\n"
    "---\n" + _SCAFFOLD_TEXT + "\n---\n\n"
    "세 가지를 본다.\n"
    "(1) description_check — description에 동사(뭘 하는지) · 대상(뭐에 대해) · 산출물"
    "(뭘 내는지) 세 요소가 있는지 본다. 있으면 note는 null, 애매하면 무엇이 부족한지 "
    "한 문장으로 적는다.\n"
    "(2) instruction_check — behavior에 다음 네 가지가 실질적으로 있는지 본다: "
    "① 트리거 조건(언제/어떤 요청에 반응하는지), ② 절차(무엇을 어떤 순서로 확인·처리"
    "하는지), ③ 도구 사용 기준(선택된 도구가 있다면 어떤 상황에서 그 도구를 쓰는지), "
    "④ 판단 기준(이 업무 도메인에서 무엇을 '문제/막힘/승인 필요'로 볼지 같은 구체적 "
    "기준값). 도구가 선택되지 않았으면 ③은 보지 않는다. 있으면 note는 null, 일부만 "
    "애매하면 무엇이 부족한지 한 문장으로 적는다. behavior가 스캐폴드 원칙과 모순되면"
    "(예: 근거 없이 답하라, 승인 없이 바로 실행하라) 그 모순도 note에 적는다.\n"
    "(3) tool_match_check — behavior 문장에서 필요해 보이는 행위와 선택된 도구를 대조한다. "
    "behavior가 요구하는데 선택하지 않은 도구가 있으면 missing_tools에, 선택했는데 "
    "behavior에서 쓰일 것 같지 않은 도구가 있으면 unused_tools에 그 도구 이름을 적는다. "
    "확실하지 않으면 비워 둔다.\n\n"
    "overall 판정:\n"
    "- reject — description과 behavior 중 하나라도 사실상 비어 있거나, '알아서', "
    "'적절히', '필요하면 처리' 같은 위임 표현뿐이라 위 ①~④ 중 단 하나도 구체적으로 "
    "추출할 수 없는 수준. 이건 다듬어서 고칠 문제가 아니라 사용자가 내용을 다시 써야 "
    "하는 문제다. reject_reason에 무엇을 채워야 하는지 한두 문장으로 적는다.\n"
    "- warn — description_check/instruction_check/tool_match_check 중 하나라도 걸리지만 "
    "그래도 다듬어서 실행 가능한 지시문을 만들 수 있는 수준.\n"
    "- pass — 셋 다 문제없음. 이미 좋은 문장을 억지로 바꿀 필요는 없다는 뜻이다.\n"
    "reject가 아니면 reject_reason은 null로 둔다."
)

_REFINE_SYSTEM_PROMPT = (
    "에이전트 빌더 지시문 보정 담당이다. 검토 담당이 behavior를 이미 'warn'으로 판정했고 "
    "무엇이 부족한지도 짚어 뒀다 — 그 지적을 반영해 behavior 문장을 실행용 지시문으로 "
    "다듬는 것만 한다. 판정은 다시 하지 않는다.\n\n"
    "아래는 이 팀의 모든 에이전트에 이미 공통으로 적용되는 스캐폴드 문구다 — 여기서 이미 "
    "다루는 내용(도구 호출 상한, 근거 원칙, 외부 변경 승인)은 다시 적지 않는다:\n"
    "---\n" + _SCAFFOLD_TEXT + "\n---\n\n"
    "behavior에 없는 지시를 새로 지어내지 않는다. 지적된 부분도 behavior가 실제로 담고 "
    "있는 내용 이상을 추측해서 채우지 않는다 — behavior에 정말 없는 정보라면 그 자리는 "
    "일반적인 문구로만 다듬고, 없는 구체적 기준값을 지어내지 않는다."
)


def _tool_view(row: dict[str, Any]) -> dict[str, str]:
    return {"name": row["name"], "description": row.get("description") or ""}


def check_definition(*, tool_refs: list[str], catalog: dict[str, dict[str, Any]]) -> str | None:
    """로컬/DB로 확정할 수 있는 항목만 본다 — 라이브 외부 호출은 안 한다.

    막힘이 있으면 사용자에게 보여줄 한 문장을 돌려주고, 없으면 `None`이다.
    이게 있으면(=`reject`) LLM은 아예 부르지 않는다(비용·응답 시간 절약).
    """

    if not tool_refs:
        return None

    seen: set[str] = set()
    duplicates: list[str] = []
    unknown: list[str] = []
    for ref in tool_refs:
        if ref in seen:
            duplicates.append(ref)
        seen.add(ref)
        if ref not in catalog:
            unknown.append(ref)

    reasons: list[str] = []
    if unknown:
        reasons.append(f"더 이상 쓸 수 없는 도구가 선택돼 있습니다: {', '.join(sorted(set(unknown)))}")
    if duplicates:
        reasons.append(f"같은 도구가 중복 선택돼 있습니다: {', '.join(sorted(set(duplicates)))}")
    return " ".join(reasons) if reasons else None


def _judge_builder_input(
    client: OpenAI,
    *,
    name: str,
    description: str,
    behavior: str,
    selected_tools: list[dict[str, Any]],
    unselected_tools: list[dict[str, Any]],
) -> BuilderJudgment:
    response = client.responses.parse(
        model=PLAN_MODEL,
        service_tier=settings.OPENAI_SERVICE_TIER,
        reasoning={"effort": "low"},
        input=[
            {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"name={name}\ndescription={description}\nbehavior={behavior}\n"
                    f"선택된 도구={[_tool_view(row) for row in selected_tools]}\n"
                    f"선택 안 한 도구={[_tool_view(row) for row in unselected_tools]}"
                ),
            },
        ],
        text_format=BuilderJudgment,
    )
    result = response.output_parsed
    if result is None:
        raise ValueError("빌더 검토 모델이 구조화 결과를 반환하지 않았습니다.")
    return result


def _refine_behavior(
    client: OpenAI,
    *,
    behavior: str,
    description_note: str | None,
    instruction_note: str | None,
) -> str:
    response = client.responses.parse(
        model=PLAN_MODEL,
        service_tier=settings.OPENAI_SERVICE_TIER,
        reasoning={"effort": "low"},
        input=[
            {"role": "system", "content": _REFINE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"behavior={behavior}\n"
                    f"검토 담당이 짚은 설명 문제={description_note}\n"
                    f"검토 담당이 짚은 지시문 문제={instruction_note}"
                ),
            },
        ],
        text_format=RefinedInstruction,
    )
    result = response.output_parsed
    if result is None:
        raise ValueError("지시문 보정 모델이 구조화 결과를 반환하지 않았습니다.")
    return result.refined_instruction


def check_builder_input(
    *,
    name: str,
    description: str,
    behavior: str,
    selected_tools: list[dict[str, Any]],
    unselected_tools: list[dict[str, Any]],
) -> BuilderCheckResult:
    """판정(1차 호출) → warn일 때만 보정(2차 호출). `pass`/`reject`는 보정 호출을
    아예 하지 않는다 — `pass`는 이미 좋아서 다듬을 게 없고, `reject`는 다듬어서 쓸
    실질 내용이 없다."""

    if not str(settings.OPENAI_API_KEY).strip():
        raise PipelineConfigurationError("필수 OpenAI 설정이 없습니다: OPENAI_API_KEY")

    client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=120, max_retries=1)
    judgment = _judge_builder_input(
        client,
        name=name,
        description=description,
        behavior=behavior,
        selected_tools=selected_tools,
        unselected_tools=unselected_tools,
    )

    # 문장을 고쳐서 실제로 풀리는 문제인가. `tool_match_check`만 걸린 warn은
    # description/instruction 문장이 이미 깨끗하다는 뜻이라, 지시문을 다시 써도
    # missing_tools/unused_tools는 하나도 안 풀린다 — 그건 도구 선택을 고쳐야
    # 풀리는 문제다(2026-08-12 실측: 도구 불일치뿐인데도 매번 재작성이 붙었다).
    has_text_issue = (
        judgment.description_check.note is not None or judgment.instruction_check.note is not None
    )

    if judgment.overall == "reject":
        refined_instruction = ""
    elif judgment.overall == "pass" or not has_text_issue:
        # 이미 문제없다고 판정했거나, 문제가 있어도 문장과는 무관하다 — 굳이
        # 재작성해서 "더 손볼 게 있다"는 인상을 주지 않는다. 원문 그대로가
        # 곧 최종 지시문이다.
        refined_instruction = behavior
    else:
        refined_instruction = _refine_behavior(
            client,
            behavior=behavior,
            description_note=judgment.description_check.note,
            instruction_note=judgment.instruction_check.note,
        )

    return BuilderCheckResult(
        refined_instruction=refined_instruction,
        description_check=judgment.description_check,
        instruction_check=judgment.instruction_check,
        tool_match_check=judgment.tool_match_check,
        overall=judgment.overall,
        reject_reason=judgment.reject_reason,
    )


def _split_catalog(
    *, tool_refs: list[str], catalog: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected_refs = set(tool_refs)
    selected = [row for ref, row in catalog.items() if ref in selected_refs]
    unselected = [row for ref, row in catalog.items() if ref not in selected_refs]
    return selected, unselected


def review_builder_input(
    *,
    name: str,
    description: str,
    behavior: str,
    tool_refs: list[str],
    catalog: dict[str, dict[str, Any]],
) -> BuilderCheckResult:
    """1단계 전체 — 코드 검증 → (통과 시) LLM 의미 검증. 하나의 흐름으로 묶는다.

    코드 검증에서 막히면 `reject`로 바로 끝내고 LLM을 부르지 않는다 — 확정 오류가
    있는 초안에 LLM 호출을 쓸 이유가 없다.
    """

    blocker = check_definition(tool_refs=tool_refs, catalog=catalog)
    if blocker is not None:
        return BuilderCheckResult(
            refined_instruction="",
            description_check=DescriptionCheck(),
            instruction_check=InstructionCheck(),
            tool_match_check=ToolMatchCheck(),
            overall="reject",
            reject_reason=blocker,
        )

    selected, unselected = _split_catalog(tool_refs=tool_refs, catalog=catalog)
    return check_builder_input(
        name=name,
        description=description,
        behavior=behavior,
        selected_tools=selected,
        unselected_tools=unselected,
    )


_INSTRUCTION_RECHECK_PROMPT = (
    "에이전트 빌더 지시문 재검토 담당이다. 사용자가 1차 검증에서 나온 제안을 보고 지시문을 "
    "스스로 고쳤다 — 설명(description)은 건드리지 않았다. 새로 다듬을 필요는 없고, 고친 "
    "지시문 자체와 도구 선택이 여전히 맞는지만 본다.\n\n"
    "아래는 이 팀의 모든 에이전트에 이미 공통으로 적용되는 스캐폴드 문구다 — 지시문이 이 "
    "내용을 반복하거나 이 내용과 모순되는지 판단할 때 참고하라:\n"
    "---\n" + _SCAFFOLD_TEXT + "\n---\n\n"
    "두 가지를 본다.\n"
    "(1) instruction_check — 지시문에 다음 네 가지가 실질적으로 있는지 본다: "
    "① 트리거 조건(언제/어떤 요청에 반응하는지), ② 절차(무엇을 어떤 순서로 확인·처리하는지), "
    "③ 도구 사용 기준(선택된 도구가 있다면 어떤 상황에서 그 도구를 쓰는지), ④ 판단 기준. "
    "도구가 선택되지 않았으면 ③은 보지 않는다. 있으면 note는 null, 일부만 애매하면 무엇이 "
    "부족한지 한 문장으로 적는다.\n"
    "(2) tool_match_check — 지시문 문장에서 필요해 보이는 행위와 선택된 도구를 대조한다. "
    "지시문이 요구하는데 선택하지 않은 도구가 있으면 missing_tools에, 선택했는데 지시문에서 "
    "쓰일 것 같지 않은 도구가 있으면 unused_tools에 적는다. 확실하지 않으면 비워 둔다.\n\n"
    "overall 판정:\n"
    "- reject — 지시문이 사실상 비어 있거나 '알아서', '적절히' 같은 위임 표현뿐이라 위 "
    "①~④ 중 단 하나도 구체적으로 추출할 수 없는 수준.\n"
    "- warn — 위 두 체크 중 하나라도 걸리지만 실행 가능한 지시문인 수준.\n"
    "- pass — 문제없음.\n"
    "reject가 아니면 reject_reason은 null로 둔다."
)


def recheck_instruction(
    *,
    instruction: str,
    selected_tools: list[dict[str, Any]],
    unselected_tools: list[dict[str, Any]],
) -> InstructionRecheckResult:
    """지시문만 빠르게 다시 확인한다 — description_check는 안 본다.

    사용자가 1단계 보정안을 보고 지시문만 고쳤을 때, 이름·설명까지 포함한 전체
    1단계를 처음부터 다시 도는 건 느리고 낭비다. `instruction_check`와
    `tool_match_check`만 재검사한다(지시문 변경으로 필요 Tool이 달라질 수 있어
    `tool_match_check`는 함께 본다).
    """

    if not str(settings.OPENAI_API_KEY).strip():
        raise PipelineConfigurationError("필수 OpenAI 설정이 없습니다: OPENAI_API_KEY")

    client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=120, max_retries=1)
    response = client.responses.parse(
        model=PLAN_MODEL,
        service_tier=settings.OPENAI_SERVICE_TIER,
        reasoning={"effort": "low"},
        input=[
            {"role": "system", "content": _INSTRUCTION_RECHECK_PROMPT},
            {
                "role": "user",
                "content": (
                    f"instruction={instruction}\n"
                    f"선택된 도구={[_tool_view(row) for row in selected_tools]}\n"
                    f"선택 안 한 도구={[_tool_view(row) for row in unselected_tools]}"
                ),
            },
        ],
        text_format=InstructionRecheckResult,
    )
    result = response.output_parsed
    if result is None:
        raise ValueError("지시문 재검토 모델이 구조화 결과를 반환하지 않았습니다.")
    return result


def review_instruction(
    *,
    instruction: str,
    tool_refs: list[str],
    catalog: dict[str, dict[str, Any]],
) -> InstructionRecheckResult:
    """지시문 재검증의 코드 검증 + LLM 검증 묶음 — `review_builder_input`의 경량판."""

    blocker = check_definition(tool_refs=tool_refs, catalog=catalog)
    if blocker is not None:
        return InstructionRecheckResult(
            instruction_check=InstructionCheck(),
            tool_match_check=ToolMatchCheck(),
            overall="reject",
            reject_reason=blocker,
        )

    selected, unselected = _split_catalog(tool_refs=tool_refs, catalog=catalog)
    return recheck_instruction(
        instruction=instruction, selected_tools=selected, unselected_tools=unselected
    )
