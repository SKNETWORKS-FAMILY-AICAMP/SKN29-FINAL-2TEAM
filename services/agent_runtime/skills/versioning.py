"""스킬 검증 영수증과 카탈로그 갱신에 쓰는 안정적인 버전 값."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from backend.db.skill_operations import SkillCatalogRevisionRepository


def catalog_revision(account_id: str) -> int:
    return SkillCatalogRevisionRepository.get(account_id)


def increment_catalog_revision(account_id: str) -> int:
    return SkillCatalogRevisionRepository.increment(account_id)


def runtime_profile_version() -> str:
    from django.conf import settings

    return settings.RUNTIME_PROFILE_VERSION or "development"


def tool_registry_version() -> str:
    from services.harness.registry import BUILTIN_TOOLS

    registry = [
        {
            "ref": ref,
            "name": tool.name,
            "description": tool.description,
            "side_effect": tool.side_effect,
            # harness.Tool의 정본 필드는 ``input_schema``다. 존재하지 않는
            # ``args_schema``를 읽으면 모든 도구 스키마가 None으로 해시되어,
            # 입력 계약이 바뀌어도 기존 검증 영수증이 계속 유효해지는 버그가 난다.
            "schema": tool.input_schema,
        }
        for ref, tool in sorted(BUILTIN_TOOLS.items())
    ]
    return hashlib.sha256(
        json.dumps(registry, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]


def validation_hash(document: dict[str, Any]) -> str:
    """저장 위치·활성 상태와 무관하지만 실행 내용 전체를 포함한 지문."""

    frontmatter = deepcopy(document.get("frontmatter")) if isinstance(document.get("frontmatter"), dict) else {}
    frontmatter["name"] = document.get("name", "")
    frontmatter["description"] = document.get("description", "")
    metadata = frontmatter.get("metadata")
    if isinstance(metadata, dict):
        operational_keys = {
            "enabled", "shared_by_account_id", "imported_from_team_id",
            "imported_from_skill_name", "validation_state", "validated_hash",
            "source_job_id", "source_revision", "runtime_profile_version",
            "tool_registry_version",
        }
        cleaned = {key: value for key, value in metadata.items() if key not in operational_keys}
        if cleaned:
            frontmatter["metadata"] = cleaned
        else:
            frontmatter.pop("metadata", None)
    payload = {"frontmatter": frontmatter, "body": document.get("body", "")}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


__all__ = [
    "catalog_revision",
    "increment_catalog_revision",
    "runtime_profile_version",
    "tool_registry_version",
    "validation_hash",
]
