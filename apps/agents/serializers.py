"""에이전트 정의 입력 검증과 API 표현."""

from typing import Any

from rest_framework import serializers

#: Builder가 고를 수 있는 모델 — 화면(`frontend/src/data/models.ts`)과 같은
#: 목록이어야 한다. `gpt-5.5-pro`·`gpt-5.4-pro`는 `effort: low`를 안 받아 빠졌다.
AGENT_MODELS = (
    "gpt-5.6-luna",
    "gpt-5.6-terra",
    "gpt-5.6-sol",
    "claude-haiku-4-5",
    "claude-sonnet-4-5",
    "claude-opus-4-5",
)
REASONING_EFFORTS = ("low", "medium", "high", "xhigh")


def builtin_tool_response() -> list[dict[str, Any]]:
    """내장 도구 목록. Registry가 정본이다 — 화면이 따로 적어 두면 어긋난다.

    `ALWAYS_ON_TOOL_REFS`(예: `skill_register`)는 안 낸다 — 모든 에이전트에
    무조건 붙는 도구라 고르고 말고가 없다. 골라야 하는 목록에 고를 필요 없는
    항목이 섞이면 "이건 꺼도 되나?"라는 오해를 만든다.
    """

    from services.harness.registry import ALWAYS_ON_TOOL_REFS, BUILTIN_TOOLS

    return [
        {
            "tool_ref": tool.ref,
            "name": tool.name,
            "description": tool.description,
            "source": "기본 제공",
            "category": tool.category,
            "side_effect": tool.side_effect,
            "input_schema": tool.input_schema,
        }
        for tool in BUILTIN_TOOLS.values()
        if tool.ref not in ALWAYS_ON_TOOL_REFS
    ]


class SubagentRefSerializer(serializers.Serializer):
    """`AgentVersionPublishSerializer.subagents`의 항목 하나.

    필드는 02 §16 요청 계약 그대로다. 빈 문자열만 여기서 막고, "이미 쓰는
    alias인지"·"활성/권한이 있는지" 같은 구조 검증은
    `services.agent_runtime.subagents.validation.validate_subagents()`가 한다
    — 저장·발행 API와 Factory가 같은 함수를 쓴다(02 §7.1).
    """

    child_agent_id = serializers.CharField(max_length=5)
    child_version_id = serializers.CharField(max_length=5)
    alias = serializers.CharField(max_length=100, trim_whitespace=True, allow_blank=False)
    delegation_description = serializers.CharField(allow_blank=False, trim_whitespace=True)


class AgentVersionPublishSerializer(serializers.Serializer):
    """새 버전 발행 입력(02 §16). "저장"과 "발행"은 한 동작이다 — `agent_versions`가
    불변이라(02 §5.2) 임시 저장이라는 중간 상태가 없다.
    """

    name = serializers.CharField(max_length=100)
    description = serializers.CharField(max_length=500, allow_blank=True, default="")
    system_prompt = serializers.CharField(allow_blank=True, default="")
    model = serializers.CharField(
        max_length=100, trim_whitespace=True, required=False, allow_null=True, default=None
    )
    reasoning_effort = serializers.ChoiceField(
        choices=REASONING_EFFORTS, required=False, allow_null=True, default=None
    )
    # max_value는 `runtime_policy.RuntimeCapabilityPolicy.max_model_calls_ceiling`
    # (services/agent_runtime/runtime_policy.py)과 같은 값으로 맞춘다 — 한쪽만
    # 올리면 저장은 되는데 실행은 그 값을 못 넘기는 죽은 설정이 된다.
    max_iterations = serializers.IntegerField(min_value=2, max_value=50, default=10)
    tool_refs = serializers.ListField(
        child=serializers.CharField(max_length=100), allow_empty=True, default=list
    )
    subagents = SubagentRefSerializer(many=True, required=False, default=list)


class AgentVersionFavoriteSerializer(serializers.Serializer):
    """즐겨찾기 별 토글 입력(2026-08-18)."""

    favorite = serializers.BooleanField()


def agent_version_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_id": row["agent_id"],
        "name": row["name"],
        "description": row.get("description") or "",
        "status": row.get("status"),
        "is_default_chat": row.get("is_default_chat", False),
        # 이 계정 기준 즐겨찾기 — 팀 전체가 아니라 요청한 계정만의 값이다.
        "is_favorite": row.get("is_favorite", False),
        "owner_account_id": row.get("owner_account_id"),
        "current_version_id": row.get("current_version_id"),
        "version": row.get("version"),
        "system_prompt": row.get("system_prompt") or "",
        "model": row.get("model"),
        "reasoning_effort": row.get("reasoning_effort"),
        "max_iterations": row.get("max_iterations"),
        "tool_refs": row.get("tool_refs") or [],
        "subagents": row.get("subagents") or [],
        # 목록 카드용 요약 — 지금 버전이 위임하는 자식 에이전트 이름만.
        "subagent_names": row.get("subagent_names") or [],
        "updated_at": row.get("updated_at"),
    }


def mcp_tool_response(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "tool_ref": row["tool_ref"],
            "name": row["name"],
            "description": row.get("description") or "",
            "source": f"MCP · {row['server_name']}",
            # MCP 도구는 읽기 전용인지 알 방법이 없어 전부 부작용으로 본다.
            "side_effect": True,
            "server_status": row.get("server_status"),
            "input_schema": row.get("input_schema") or {"type": "object", "properties": {}},
        }
        for row in rows
    ]
