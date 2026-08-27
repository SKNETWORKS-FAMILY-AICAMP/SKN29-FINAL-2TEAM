"""손실 없이 읽고 다시 쓰는 Agent Skills ``SKILL.md`` 모델."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any, Mapping

import yaml


@dataclass(frozen=True)
class SkillDocument:
    name: str
    description: str
    body: str
    frontmatter: dict[str, Any]

    @classmethod
    def parse(cls, content: str) -> "SkillDocument":
        if not content.startswith("---\n"):
            raise ValueError("frontmatter(---로 시작하는 부분)가 없습니다.")
        end = content.find("\n---", 4)
        if end == -1:
            raise ValueError("frontmatter가 닫히지 않았습니다.")
        try:
            # BaseLoader는 날짜·불리언을 Python 전용 객체로 바꾸지 않아 job의
            # JSONB에도 안전하며, 목록·중첩 구조는 그대로 보존한다.
            raw = yaml.load(content[4:end], Loader=yaml.BaseLoader) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"frontmatter를 읽을 수 없습니다: {exc}") from exc
        if not isinstance(raw, dict):
            raise ValueError("frontmatter 형식이 올바르지 않습니다.")
        name = str(raw.get("name") or "").strip()
        description = str(raw.get("description") or "").strip()
        if not name:
            raise ValueError("파일의 frontmatter에 name이 없습니다.")
        if not description:
            raise ValueError("파일의 frontmatter에 description이 없습니다.")
        body = content[end + 4 :]
        body = body[1:] if body.startswith("\n") else body
        return cls(name=name, description=description, body=body.strip("\n"), frontmatter=deepcopy(raw))

    @classmethod
    def create(
        cls,
        *,
        name: str,
        description: str,
        body: str,
        frontmatter: Mapping[str, Any] | None = None,
    ) -> "SkillDocument":
        raw = deepcopy(dict(frontmatter or {}))
        raw["name"] = name
        raw["description"] = description
        return cls(name=name, description=description, body=body, frontmatter=raw)

    @property
    def metadata(self) -> dict[str, Any]:
        value = self.frontmatter.get("metadata")
        return deepcopy(value) if isinstance(value, dict) else {}

    @property
    def enabled(self) -> bool:
        return str(self.metadata.get("enabled", "true")).strip().lower() != "false"

    def updated(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        body: str | None = None,
        enabled: bool | None = None,
        metadata_updates: Mapping[str, Any] | None = None,
    ) -> "SkillDocument":
        next_name = self.name if name is None else name
        next_description = self.description if description is None else description
        raw = deepcopy(self.frontmatter)
        raw["name"] = next_name
        raw["description"] = next_description
        metadata = raw.get("metadata")
        metadata = deepcopy(metadata) if isinstance(metadata, dict) else {}
        if enabled is not None:
            metadata["enabled"] = "true" if enabled else "false"
        if metadata_updates:
            for key, value in metadata_updates.items():
                if value is None:
                    metadata.pop(key, None)
                else:
                    metadata[key] = value
        if metadata:
            raw["metadata"] = metadata
        else:
            raw.pop("metadata", None)
        return replace(
            self,
            name=next_name,
            description=next_description,
            body=self.body if body is None else body,
            frontmatter=raw,
        )

    def render(self) -> str:
        frontmatter = yaml.safe_dump(
            self.frontmatter,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
        return f"---\n{frontmatter}---\n\n{self.body}\n"


__all__ = ["SkillDocument"]
