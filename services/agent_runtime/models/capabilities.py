"""에이전트 모델의 입력 capability 정본."""

from __future__ import annotations

from backend.db.agent_platform import CustomModelRepository


BUILTIN_IMAGE_INPUT_MODELS = frozenset(
    {
        "gpt-5.6-luna",
        "gpt-5.6-terra",
        "gpt-5.6-sol",
        "claude-haiku-4-5",
        "claude-sonnet-4-5",
        "claude-opus-4-5",
    }
)

IMAGE_DOCUMENT_SEARCH_TOOL_REF = "document_search_with_images"


def supports_image_input(*, model: str | None, team_id: str | None = None) -> bool:
    """기본 모델 또는 팀 커스텀 모델이 이미지 입력을 받는지 반환한다."""

    if not model:
        return False
    if model in BUILTIN_IMAGE_INPUT_MODELS:
        return True
    if not team_id:
        return False
    custom = CustomModelRepository.for_model(team_id, model)
    return bool(custom and custom.get("supports_image_input") is True)


__all__ = [
    "BUILTIN_IMAGE_INPUT_MODELS",
    "IMAGE_DOCUMENT_SEARCH_TOOL_REF",
    "supports_image_input",
]
