"""에이전트 CRUD 입력 검증과 API 표현."""

from typing import TYPE_CHECKING, Any

from rest_framework import serializers

if TYPE_CHECKING:
    from services.agent_builder import BuilderCheckResult, InstructionRecheckResult

#: Builder 가 고를 수 있는 모델. `services/task_extraction.SUPPORTED_MODELS` 와
#: 같은 목록이어야 한다 — 없는 모델을 저장하면 실행 시점에야 터진다.
AGENT_MODELS = ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol")
REASONING_EFFORTS = ("low", "medium", "high", "xhigh")


class AgentWriteSerializer(serializers.Serializer):
    """생성·수정 공통.

    `is_prebuilt` 는 받지 않는다. 화면에서 켤 수 있으면 「우리가 제공하는 것」과
    「팀이 만든 것」의 구분이 무의미해진다(1차 단계 4와 같은 이유).
    """

    name = serializers.CharField(max_length=100)
    description = serializers.CharField(max_length=500, allow_blank=True, default="")
    instruction = serializers.CharField(allow_blank=True, default="")
    model = serializers.ChoiceField(choices=AGENT_MODELS, default="gpt-5.6-luna")
    reasoning_effort = serializers.ChoiceField(choices=REASONING_EFFORTS, default="low")
    # 폭주를 막는 값이다. 1 이면 도구를 한 번도 못 쓰고, 크면 실패할 때 그만큼
    # 오래 헛돈다.
    max_iterations = serializers.IntegerField(min_value=2, max_value=20, default=6)
    tool_refs = serializers.ListField(
        child=serializers.CharField(max_length=100), allow_empty=True, default=list
    )


def agent_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_id": row["agent_id"],
        "name": row["name"],
        "description": row.get("description") or "",
        "instruction": row.get("instruction") or "",
        "model": row.get("model"),
        "reasoning_effort": row.get("reasoning_effort"),
        "max_iterations": row.get("max_iterations"),
        "is_prebuilt": row.get("is_prebuilt", False),
        # DRAFT / ACTIVE / DISABLED. ARCHIVED 행은 `list_for_team`이 애초에
        # 안 돌려주므로 여기 오지 않는다.
        "status": row.get("status"),
        "owner_name": row.get("owner_name"),
        "updated_at": row.get("updated_at"),
        "tool_refs": row.get("tool_refs") or [],
    }


def builtin_tool_response() -> list[dict[str, Any]]:
    """내장 도구 목록. **Registry 가 정본이다** — 화면이 따로 적어 두면 어긋난다."""

    from services.harness.registry import BUILTIN_TOOLS

    return [
        {
            "tool_ref": tool.ref,
            "name": tool.name,
            "description": tool.description,
            "source": "기본 제공",
            # 승인 게이트를 타는 도구인지 화면이 알아야 「승인 필요」를 표시한다.
            "side_effect": tool.side_effect,
            # 「도구 확인」 패널이 입력 폼을 자동 생성하는 데 쓴다.
            "input_schema": tool.input_schema,
        }
        for tool in BUILTIN_TOOLS.values()
    ]


class BuilderCheckSerializer(serializers.Serializer):
    """`AgentBuilderCheckAPIView` 입력. 저장 여부와 무관하게 언제든 다시 부를 수 있다."""

    name = serializers.CharField(max_length=100)
    description = serializers.CharField(max_length=500, allow_blank=True, default="")
    behavior = serializers.CharField(allow_blank=False)
    tool_refs = serializers.ListField(
        child=serializers.CharField(max_length=100), allow_empty=True, default=list
    )


class BuilderTestRunSerializer(serializers.Serializer):
    """`AgentBuilderTestRunAPIView` 입력. 저장하지 않은 설정 그대로 한 번 돌려 본다."""

    instruction = serializers.CharField(allow_blank=True, default="")
    tool_refs = serializers.ListField(
        child=serializers.CharField(max_length=100), allow_empty=True, default=list
    )
    model = serializers.ChoiceField(choices=AGENT_MODELS, required=False, allow_null=True, default=None)
    reasoning_effort = serializers.ChoiceField(
        choices=REASONING_EFFORTS, required=False, allow_null=True, default=None
    )
    max_iterations = serializers.IntegerField(min_value=2, max_value=20, default=6)
    user_input = serializers.CharField(allow_blank=False)


class BuilderToolCheckSerializer(serializers.Serializer):
    """`AgentBuilderToolCheckAPIView` 입력. 선택한 도구를 모델 없이 직접 불러 본다."""

    tool_refs = serializers.ListField(
        child=serializers.CharField(max_length=100), allow_empty=False
    )
    arguments = serializers.DictField(child=serializers.JSONField(), default=dict)


class BuilderInstructionRecheckSerializer(serializers.Serializer):
    """`AgentBuilderInstructionRecheckAPIView` 입력.

    사용자가 1단계 보정안을 보고 지시문만 고쳤을 때 쓴다 — description은 안 받는다.
    """

    instruction = serializers.CharField(allow_blank=False)
    tool_refs = serializers.ListField(
        child=serializers.CharField(max_length=100), allow_empty=True, default=list
    )


def builder_check_response(result: "BuilderCheckResult") -> dict[str, Any]:
    return {
        "refined_instruction": result.refined_instruction,
        "description_check": {"note": result.description_check.note},
        "instruction_check": {"note": result.instruction_check.note},
        "tool_match_check": {
            "missing_tools": result.tool_match_check.missing_tools,
            "unused_tools": result.tool_match_check.unused_tools,
        },
        "overall": result.overall,
        "reject_reason": result.reject_reason,
    }


def builder_instruction_recheck_response(result: "InstructionRecheckResult") -> dict[str, Any]:
    return {
        "instruction_check": {"note": result.instruction_check.note},
        "tool_match_check": {
            "missing_tools": result.tool_match_check.missing_tools,
            "unused_tools": result.tool_match_check.unused_tools,
        },
        "overall": result.overall,
        "reject_reason": result.reject_reason,
    }


def mcp_tool_response(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "tool_ref": row["tool_ref"],
            "name": row["name"],
            "description": row.get("description") or "",
            "source": f"MCP · {row['server_name']}",
            # MCP 도구는 읽기 전용인지 알 방법이 없어 전부 부작용으로 본다
            # (11_MCP_설계 §4 — 모르는 것은 안전한 쪽으로).
            "side_effect": True,
            "server_status": row.get("server_status"),
        }
        for row in rows
    ]
