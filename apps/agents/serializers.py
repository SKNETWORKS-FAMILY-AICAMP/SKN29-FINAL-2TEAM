"""에이전트 CRUD 입력 검증과 API 표현."""

from typing import Any

from rest_framework import serializers

#: Builder 가 고를 수 있는 모델. `services/task_extraction.SUPPORTED_MODELS` 와
#: 같은 목록이어야 한다 — 없는 모델을 저장하면 실행 시점에야 터진다.
#: 고를 수 있는 모델. **계정에 있는 것이 아니라 우리 호출 방식으로 실제로 도는
#: 것**만 넣는다(2026-08-12 실측 — `responses.create` + tools + reasoning).
#:
#: `gpt-5.5-pro`·`gpt-5.4-pro` 는 목록에는 있지만 뺐다. **`effort: low` 를 안 받아
#: 400 이 난다.** 응답 방식을 따로 고르게 해 두었으므로 조합이 깨진다 — 고를 수
#: 있는데 실행하면 죽는 값은 없느니만 못하다.
#:
#: 화면(`frontend/src/data/models.ts`)과 **같은 목록이어야 한다.** 예전에는 Model
#: 탭·Builder·여기가 각각 달랐다(Model 탭에는 계정에 없는 `gpt-5-mini` 가 있었다).
AGENT_MODELS = (
    "gpt-5.6-luna",
    "gpt-5.6-terra",
    "gpt-5.6-sol",
    "claude-haiku-4-5",
    "claude-sonnet-4-5",
    "claude-opus-4-5",
)
REASONING_EFFORTS = ("low", "medium", "high", "xhigh")


class AgentWriteSerializer(serializers.Serializer):
    """생성·수정 공통.

    `is_prebuilt` 는 받지 않는다. 화면에서 켤 수 있으면 「우리가 제공하는 것」과
    「팀이 만든 것」의 구분이 무의미해진다(1차 단계 4와 같은 이유).
    """

    name = serializers.CharField(max_length=100)
    description = serializers.CharField(max_length=500, allow_blank=True, default="")
    instruction = serializers.CharField(allow_blank=True, default="")
    # **`ChoiceField` 가 아니다** — 무엇이
    # 유효한지는 팀마다 다르고(등록한 커스텀 모델이 있다), 뷰가 대조한다.
    model = serializers.CharField(max_length=100, trim_whitespace=True, default="gpt-5.6-luna")
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
            # 선택 화면이 묶어 보여줄 단위(2026-08-18) — 저장·실행에는 안 쓴다.
            "category": tool.category,
            # 승인 게이트를 타는 도구인지 화면이 알아야 「승인 필요」를 표시한다.
            "side_effect": tool.side_effect,
            # 「도구 확인」 패널이 입력 폼을 자동 생성하는 데 쓴다.
            "input_schema": tool.input_schema,
        }
        for tool in BUILTIN_TOOLS.values()
    ]


class BuilderTestRunSerializer(serializers.Serializer):
    """`AgentBuilderTestRunAPIView` 입력. 저장하지 않은 설정 그대로 한 번 돌려 본다."""

    instruction = serializers.CharField(allow_blank=True, default="")
    tool_refs = serializers.ListField(
        child=serializers.CharField(max_length=100), allow_empty=True, default=list
    )
    # `AgentWriteSerializer.model` 과 같다 — 뷰가 팀 목록과 대조한다. 시험 실행에서
    # 못 고르는 모델이 있으면, 저장은 되는데 시험은 안 되는 짝이 어긋난 화면이 된다.
    model = serializers.CharField(
        max_length=100, trim_whitespace=True, required=False, allow_null=True, default=None
    )
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


class SubagentRefSerializer(serializers.Serializer):
    """`AgentVersionPublishSerializer.subagents`의 항목 하나.

    필드는 02 §16 요청 계약 그대로다. `alias`/`delegation_description`을 여기서
    빈 문자열까지만 막고, "이미 쓰는 alias인지"·"활성/권한이 있는지" 같은 구조
    검증은 `services.agent_runtime.subagents.validation.validate_subagents()`가
    한다 — 저장·발행 API와 Factory가 같은 함수를 쓴다(02 §7.1).
    """

    child_agent_id = serializers.CharField(max_length=5)
    child_version_id = serializers.CharField(max_length=5)
    alias = serializers.CharField(max_length=100, trim_whitespace=True, allow_blank=False)
    delegation_description = serializers.CharField(allow_blank=False, trim_whitespace=True)


class AgentVersionPublishSerializer(serializers.Serializer):
    """새 버전 발행 입력(02 §16). "저장"과 "발행"은 한 동작이다 — `agent_versions`가
    불변이라(02 §5.2) 임시 저장이라는 중간 상태가 없다.

    `AgentWriteSerializer`(옛 비버전 스키마용)와 겹치는 필드가 많지만 따로 둔다
    — `instruction`이 아니라 `system_prompt`이고, `subagents`가 추가됐고, 두
    스키마는 서로 다른 테이블로 간다.
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
    max_iterations = serializers.IntegerField(min_value=2, max_value=20, default=6)
    tool_refs = serializers.ListField(
        child=serializers.CharField(max_length=100), allow_empty=True, default=list
    )
    subagents = SubagentRefSerializer(many=True, required=False, default=list)


class AgentVersionFavoriteSerializer(serializers.Serializer):
    """즐겨찾기 별 토글 입력(2026-08-18). 켜고 끄는 값 하나뿐이라 단순하다 —
    활성화·중지처럼 서버 재검증이 필요한 상태 전이가 아니다."""

    favorite = serializers.BooleanField()


def agent_version_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_id": row["agent_id"],
        "name": row["name"],
        "description": row.get("description") or "",
        "status": row.get("status"),
        "is_default_chat": row.get("is_default_chat", False),
        # 이 계정 기준 즐겨찾기(2026-08-18) — 팀 전체가 아니라 요청한 계정만의
        # 값이다(`agent_favorites`, `list_for_team()`/`get()` 참고).
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
        # `list_for_team()`만 채운다(json_agg); 상세 조회는 `subagents`에
        # alias·위임 설명까지 이미 있어 따로 안 채운다.
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
            # MCP 도구는 읽기 전용인지 알 방법이 없어 전부 부작용으로 본다
            # (11_MCP_설계 §4 — 모르는 것은 안전한 쪽으로).
            "side_effect": True,
            "server_status": row.get("server_status"),
            # 「도구 확인」 패널이 입력 폼을 만드는 데 쓴다. 저장된 스키마가
            # 비어 있으면 프런트가 빈 객체 스키마로 다룰 수 있게 최소 형태로 채운다.
            "input_schema": row.get("input_schema") or {"type": "object", "properties": {}},
        }
        for row in rows
    ]
