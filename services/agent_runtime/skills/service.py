"""Skill 생성·조회·수정·삭제 — 채팅 `skill_register` 도구와 설정 화면 REST API가
공유하는 단일 진실 공급원.

여태 이 로직은 `services/harness/registry.py`의 `_skill_register` 안에만
있었다(채팅에서 "스킬로 등록해줘" 라고 했을 때 `HumanInTheLoopMiddleware` 확인
카드를 거쳐 부르는 도구). 그런데 설정 > 스킬 화면(`SkillsTab.tsx`)은 그 도구를
거치지 않고 **직접** 스킬을 만들고·읽고·고치고·지운다 — 개인 스킬은 원래
설계(`2026-08-20_16_Skill_Middleware_설계.md`)부터 "승인 버튼 필요없이 바로
등록"이라 화면에서 곧장 저장해도 되고, 미리보기+저장 버튼이 있는 그 화면
자체가 이미 "미리보기 후 등록" 요건을 채운다.

같은 저장 규칙(이름 검증, frontmatter 형식, 저장 경로)을 두 곳에 따로 적으면
언젠가 어긋난다 — 그래서 여기 하나로 모으고, 도구도 REST 뷰도 이 모듈만 부른다.

**`StoreBackend`를 explicit `store=`로 초기화해 쓴다** — deepagents가 이미
구현한 backend를 그대로 재사용한다(2026-08-21 Skill Middleware 설계에서
정한 원칙과 같다: 새 저장 로직을 만들지 않는다). `StoreBackend.__init__`
docstring에 명시된 대로, `store`를 직접 주면 LangGraph 그래프 실행 컨텍스트
밖에서도(Django 뷰 안에서도) 그대로 쓸 수 있다 — `get_store()`가 요구하는
그래프 컨텍스트가 필요 없어진다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

MAX_SKILL_NAME_LENGTH = 64
MAX_SKILL_DESCRIPTION_LENGTH = 1024

#: **deepagents의 진짜 상한을 근거로 정했다** — `deepagents/middleware/skills.py`의
#: `MAX_SKILL_FILE_SIZE = 10 * 1024 * 1024`(SKILL.md 파일 전체 10MB)를 실측
#: 확인했다. 그 상한을 넘기면 `_parse_skill_metadata`가 `logger.warning`만 남기고
#: `None`을 돌려주는데, 호출부(`_list_skills_with_errors`)는 `None`을 그냥
#: 건너뛴다 — `skills_load_errors`에도 안 남는다. 즉 **넘긴 스킬은 사람에게
#: 아무 신호 없이 조용히 사라진다.** 여기서 훨씬 낮게(10MB의 1/50) 잡아서
#: 저장 시점에 분명한 오류로 막는다 — 절차 문서 하나가 200KB를 넘을 일은
#: 실무에서 거의 없다.
MAX_SKILL_BODY_BYTES = 200 * 1024

#: deepagents의 private `_validate_skill_name`(`deepagents/middleware/skills.py`)과
#: 같은 규칙 — 소문자 영숫자와 하이픈만, 앞뒤/연속 하이픈 금지. private 함수라
#: import하지 않고 재구현한다(이 프로젝트가 deepagents의 공개 이름만 가져다
#: 쓴다는 원칙 — 2026-08-21 Skill Middleware 구현 때 정함).
_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class SkillError(ValueError):
    """사람에게 그대로 보여줘도 되는 실패. `ToolInputError`와 DRF 응답 양쪽이
    메시지를 그대로 쓴다 — 여기서 한 번만 한국어 문구를 정한다."""


class SkillNotFound(SkillError):
    pass


class SkillNameConflict(SkillError):
    """2026-08-22 결정 — 업로드/작성한 이름이 이미 있으면 **덮어쓰지 않고
    거부한다.** 조용히 덮어쓰면 다른 스킬을 고치려던 게 아닌데 지워질 수 있다."""


class SkillPermissionDenied(SkillError):
    pass


def validate_skill_name(name: str) -> str | None:
    """문제가 있으면 사람에게 보여줄 한국어 문구를, 없으면 `None`을 돌려준다."""

    if not name or len(name) > MAX_SKILL_NAME_LENGTH:
        return f"스킬 이름은 1~{MAX_SKILL_NAME_LENGTH}자여야 합니다."
    if not _NAME_RE.match(name):
        return "스킬 이름은 소문자, 숫자, 하이픈(-)만 쓸 수 있고 하이픈으로 시작·끝나거나 연속될 수 없습니다."
    return None


def _validate_description(description: str) -> None:
    if not description or not description.strip():
        raise SkillError("스킬 설명이 비어 있습니다.")
    if len(description) > MAX_SKILL_DESCRIPTION_LENGTH:
        raise SkillError(f"스킬 설명은 {MAX_SKILL_DESCRIPTION_LENGTH}자를 넘을 수 없습니다.")


def _validate_body(body: str) -> None:
    if not body or not body.strip():
        raise SkillError("스킬 본문이 비어 있습니다.")
    size = len(body.encode("utf-8"))
    if size > MAX_SKILL_BODY_BYTES:
        limit_kb = MAX_SKILL_BODY_BYTES // 1024
        raise SkillError(f"스킬 본문은 {limit_kb}KB를 넘을 수 없습니다. (지금 약 {size // 1024}KB)")


@dataclass(frozen=True)
class _Scope:
    """어느 저장 공간을 볼지 — 개인(`account_id`) 또는 팀(`team_id`)."""

    prefix: str
    namespace: tuple[str, ...]


def _personal_scope(account_id: str) -> _Scope:
    from .backend import SKILLS_PERSONAL_PATH_PREFIX, personal_namespace

    return _Scope(prefix=SKILLS_PERSONAL_PATH_PREFIX, namespace=personal_namespace(account_id))


def _team_scope(team_id: str) -> _Scope:
    from .backend import SKILLS_TEAM_PATH_PREFIX, team_namespace

    return _Scope(prefix=SKILLS_TEAM_PATH_PREFIX, namespace=team_namespace(team_id))


def _store_backend(scope: _Scope) -> Any:
    from deepagents.backends import StoreBackend

    from services.agent_runtime.memory.store import get_memory_store

    return StoreBackend(namespace=lambda _rt: scope.namespace, store=get_memory_store())


def _render_skill_md(*, name: str, description: str, body: str) -> str:
    import yaml

    frontmatter = yaml.safe_dump(
        {"name": name, "description": description}, allow_unicode=True, default_flow_style=False
    )
    return f"---\n{frontmatter}---\n\n{body}\n"


def parse_skill_md(content: str) -> tuple[str, str, str]:
    """`---\\nyaml\\n---\\n\\nbody` 형식을 `(name, description, body)`로 나눈다.

    업로드 탭에서 쓴다 — 사람이 올리는 `.md` 파일은 이미 frontmatter를 담고
    있어서, 만들 때와 달리 **읽어서** 이름·설명을 꺼내야 한다(Claude의 스킬
    업로드가 파일 안 frontmatter에서 이름을 가져오는 것과 같은 방식,
    2026-08-22 확인). 여기서 나온 세 값은 그대로 `create_skill()`에 넘긴다 —
    저장 형식은 항상 이 모듈이 다시 만든 frontmatter 하나로 통일한다.
    """

    if not content.startswith("---\n"):
        raise SkillError("스킬 파일 형식이 올바르지 않습니다 — frontmatter(---로 시작하는 부분)가 없습니다.")
    end = content.find("\n---", 4)
    if end == -1:
        raise SkillError("스킬 파일 형식이 올바르지 않습니다 — frontmatter가 닫히지 않았습니다.")

    import yaml

    try:
        frontmatter = yaml.safe_load(content[4:end]) or {}
    except yaml.YAMLError as exc:
        raise SkillError(f"frontmatter를 읽을 수 없습니다: {exc}") from exc
    if not isinstance(frontmatter, dict):
        raise SkillError("frontmatter 형식이 올바르지 않습니다.")

    name = str(frontmatter.get("name") or "").strip()
    description = str(frontmatter.get("description") or "").strip()
    if not name:
        raise SkillError("파일의 frontmatter에 name이 없습니다.")
    if not description:
        raise SkillError("파일의 frontmatter에 description이 없습니다.")

    body = content[end + 4 :]
    # frontmatter를 닫는 `---` 뒤 첫 줄바꿈까지만 건너뛴다.
    body = body[1:] if body.startswith("\n") else body
    return name, description, body.strip("\n")


def _skill_response(*, skill_id: str, name: str, description: str, updated_at: str | None, body: str | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "skill_id": skill_id,
        "name": name,
        "description": description,
        "updated_at": updated_at,
    }
    if body is not None:
        row["body"] = body
    return row


def _read_skill(backend: Any, scope: _Scope, name: str, *, include_body: bool) -> dict[str, Any] | None:
    from .backend import skill_md_path

    # `backend.read()`가 돌려주는 `ReadResult`는 dataclass다(속성 접근) — 그
    # 안의 `file_data`는 TypedDict라 그쪽만 `["..."]`로 읽는다. deepagents
    # backend 프로토콜(`deepagents/backends/protocol.py`)이 실제로 이렇게
    # 나뉜 걸 직접 확인하고 맞췄다.
    read = backend.read(skill_md_path(scope.prefix, name))
    if read.error:
        return None
    file_data = read.file_data
    try:
        _, description, body = parse_skill_md(file_data["content"])
    except SkillError:
        return None
    return _skill_response(
        skill_id=name,
        name=name,
        description=description,
        updated_at=file_data.get("modified_at"),
        body=body if include_body else None,
    )


def list_skills(scope: _Scope) -> list[dict[str, Any]]:
    backend = _store_backend(scope)
    entries = backend.ls(scope.prefix).entries or []
    skills: list[dict[str, Any]] = []
    for entry in entries:
        if not entry["is_dir"]:
            continue
        name = entry["path"][len(scope.prefix) :].rstrip("/")
        row = _read_skill(backend, scope, name, include_body=False)
        if row is not None:
            skills.append(row)
    skills.sort(key=lambda row: row["name"])
    return skills


def get_skill(scope: _Scope, name: str) -> dict[str, Any]:
    backend = _store_backend(scope)
    row = _read_skill(backend, scope, name, include_body=True)
    if row is None:
        raise SkillNotFound("스킬을 찾을 수 없습니다.")
    return row


def _exists(scope: _Scope, name: str) -> bool:
    from .backend import skill_md_path

    backend = _store_backend(scope)
    return backend.read(skill_md_path(scope.prefix, name)).error is None


def create_skill(
    scope: _Scope, *, name: str, description: str, body: str, shadow_scope: _Scope | None = None
) -> dict[str, Any]:
    """`shadow_scope`가 있으면 그쪽에도 같은 이름이 있는지 먼저 본다.

    **`SkillsMiddleware`는 이름이 같으면 나중 소스가 앞 소스를 완전히
    덮어쓴다**(`deepagents/middleware/skills.py` `before_agent()` 실측 —
    `all_skills[skill["name"]] = skill`로 딕셔너리에 겹쳐 쓴다. `(팀)`/`(개인)`
    같은 구분 표시는 없다). 소스 순서(`skill_sources()`)가 팀을 나중에 두므로,
    이름이 겹치면 **팀 스킬이 개인 스킬을 완전히 가린다** — 개인 스킬은 그
    세션 동안 에이전트에게 아예 안 보인다(오류도 안 뜬다). 만드는 시점에 이미
    있는 쪽을 확인해 막을 수 있으면 막는다 — 여기서 못 잡는 경우(다른 팀원이
    나중에 같은 이름으로 팀 스킬을 만드는 경우)는 화면에서 같은 이름을 표시로
    알린다(`SkillsTab.tsx`).
    """
    from .backend import skill_md_path

    name_error = validate_skill_name(name)
    if name_error:
        raise SkillError(name_error)
    _validate_description(description)
    _validate_body(body)

    backend = _store_backend(scope)
    path = skill_md_path(scope.prefix, name)
    if backend.read(path).error is None:
        raise SkillNameConflict(f"이미 '{name}' 이름의 스킬이 있습니다. 다른 이름을 써주세요.")
    if shadow_scope is not None and _exists(shadow_scope, name):
        raise SkillNameConflict(
            f"이미 '{name}' 이름의 팀 스킬이 있습니다. 같은 이름으로 개인 스킬을 만들면 "
            "팀 스킬에 가려져 에이전트가 이 스킬을 못 봅니다. 다른 이름을 써주세요."
        )

    content = _render_skill_md(name=name, description=description, body=body)
    backend.write(path, content)
    return get_skill(scope, name)


def update_skill(scope: _Scope, name: str, *, description: str | None = None, body: str | None = None) -> dict[str, Any]:
    from .backend import skill_md_path

    current = get_skill(scope, name)  # SkillNotFound가 여기서 난다.
    next_description = description if description is not None else current["description"]
    next_body = body if body is not None else current["body"]
    _validate_description(next_description)
    _validate_body(next_body)

    backend = _store_backend(scope)
    content = _render_skill_md(name=name, description=next_description, body=next_body)
    backend.write(skill_md_path(scope.prefix, name), content)
    return get_skill(scope, name)


def delete_skill(scope: _Scope, name: str) -> None:
    from .backend import skill_md_path

    backend = _store_backend(scope)
    result = backend.delete(skill_md_path(scope.prefix, name))
    if result.error:
        raise SkillNotFound("스킬을 찾을 수 없습니다.")


# ---------------------------------------------------------------------------
# 개인 스킬 — account_id만 있으면 항상 허용(승인 없음, 원래 설계 그대로).
# ---------------------------------------------------------------------------


def list_personal_skills(account_id: str) -> list[dict[str, Any]]:
    return list_skills(_personal_scope(account_id))


def get_personal_skill(account_id: str, name: str) -> dict[str, Any]:
    return get_skill(_personal_scope(account_id), name)


def create_personal_skill(
    account_id: str, *, team_id: str, name: str, description: str, body: str
) -> dict[str, Any]:
    """`team_id`로 같은 이름의 팀 스킬이 있는지 먼저 본다 — `create_skill` docstring 참고."""
    return create_skill(
        _personal_scope(account_id), name=name, description=description, body=body, shadow_scope=_team_scope(team_id)
    )


def update_personal_skill(account_id: str, name: str, *, description: str | None = None, body: str | None = None) -> dict[str, Any]:
    return update_skill(_personal_scope(account_id), name, description=description, body=body)


def delete_personal_skill(account_id: str, name: str) -> None:
    delete_skill(_personal_scope(account_id), name)


# ---------------------------------------------------------------------------
# 팀 스킬 — 조회는 팀원 전체, 쓰기(생성·수정·삭제)는 leader만
# (`2026-08-20_16_Skill_Middleware_설계.md` "팀 스킬" 절 — 팀원이 팀 스킬로
# 등록해달라고 하는 경로 자체가 없다).
# ---------------------------------------------------------------------------


def _require_leader(actor_role: str) -> None:
    if actor_role != "leader":
        raise SkillPermissionDenied("팀 스킬은 팀장만 만들고 고치고 지울 수 있습니다.")


def list_team_skills(team_id: str) -> list[dict[str, Any]]:
    return list_skills(_team_scope(team_id))


def get_team_skill(team_id: str, name: str) -> dict[str, Any]:
    return get_skill(_team_scope(team_id), name)


def create_team_skill(team_id: str, *, actor_role: str, name: str, description: str, body: str) -> dict[str, Any]:
    _require_leader(actor_role)
    return create_skill(_team_scope(team_id), name=name, description=description, body=body)


def update_team_skill(
    team_id: str, name: str, *, actor_role: str, description: str | None = None, body: str | None = None
) -> dict[str, Any]:
    _require_leader(actor_role)
    return update_skill(_team_scope(team_id), name, description=description, body=body)


def delete_team_skill(team_id: str, name: str, *, actor_role: str) -> None:
    _require_leader(actor_role)
    delete_skill(_team_scope(team_id), name)


__all__ = [
    "MAX_SKILL_NAME_LENGTH",
    "MAX_SKILL_DESCRIPTION_LENGTH",
    "MAX_SKILL_BODY_BYTES",
    "SkillError",
    "SkillNotFound",
    "SkillNameConflict",
    "SkillPermissionDenied",
    "validate_skill_name",
    "parse_skill_md",
    "list_personal_skills",
    "get_personal_skill",
    "create_personal_skill",
    "update_personal_skill",
    "delete_personal_skill",
    "list_team_skills",
    "get_team_skill",
    "create_team_skill",
    "update_team_skill",
    "delete_team_skill",
]
