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


class MainModelSerializer(serializers.Serializer):
    """쓸 모델 하나.

    **`ChoiceField` 를 쓰지 않는다.** 기본 제공 6종만 허용하면 팀이 등록한
    커스텀 모델을 고를 수 없다 — 실제로 제미나이를 고르니 「유효하지 않은
    선택입니다」로 거절됐다(2026-08-12). 무엇이 유효한지는 팀마다 다르므로
    뷰가 그 팀의 목록과 대조한다.
    """

    model = serializers.CharField(max_length=100, trim_whitespace=True)


class CustomModelSerializer(serializers.Serializer):
    """팀이 직접 등록하는 모델 API.

    `base_url` 은 OpenAI 호환 경로(`/chat/completions`)여야 한다 —
    OpenRouter·Groq·Together·Azure·사내 vLLM 이 전부 그 모양이다. 모델 이름은
    우리가 알 수 없으므로 함께 받는다.
    """

    label = serializers.CharField(max_length=60, trim_whitespace=True)
    base_url = serializers.URLField(max_length=300)
    api_key = serializers.CharField(max_length=200, trim_whitespace=True)
    model = serializers.CharField(max_length=100, trim_whitespace=True)

    def validate_model(self, value):
        """**이미 제공하는 이름은 못 쓴다.**

        같은 이름이 들어오면 메인 모델 표에 같은 줄이 둘 생기고, 어느 경로로
        도는지 사람이 알 수 없다. 경로는 모델 이름 하나로 정해지므로 이름이
        겹치는 순간 그 선택은 뜻을 잃는다(2026-08-12 PM 지적).
        """

        if value in AGENT_MODELS:
            raise serializers.ValidationError(
                f"{value} 는 이미 기본 제공하는 모델입니다. 다른 모델을 고르세요."
            )
        return value


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
        }
        for tool in BUILTIN_TOOLS.values()
    ]


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
