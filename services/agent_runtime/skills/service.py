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

import logging
import re
from dataclasses import dataclass
from typing import Any

from .document import SkillDocument

logger = logging.getLogger(__name__)

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


def validate_skill_name(name: str, *, allow_reserved: bool = False) -> str | None:
    """문제가 있으면 사람에게 보여줄 한국어 문구를, 없으면 `None`을 돌려준다.

    `allow_reserved`(2026-08-24, skill-creator 기본 등록)는 내장 스킬을
    씨딩하는 `ensure_builtin_skill_creator()`만 `True`로 부른다 — 사람이
    개인 스킬을 만들 때(`create_personal_skill`)는
    항상 기본값(`False`)이라 예약된 이름을 못 쓴다.
    """

    if not name or len(name) > MAX_SKILL_NAME_LENGTH:
        return f"스킬 이름은 1~{MAX_SKILL_NAME_LENGTH}자여야 합니다."
    if not _NAME_RE.match(name):
        return "스킬 이름은 소문자, 숫자, 하이픈(-)만 쓸 수 있고 하이픈으로 시작·끝나거나 연속될 수 없습니다."
    if not allow_reserved:
        from .backend import RESERVED_SKILL_NAMES

        if name in RESERVED_SKILL_NAMES:
            return f"'{name}'은(는) 시스템이 기본 제공하는 스킬 이름이라 쓸 수 없습니다."
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


def _builtin_scope() -> _Scope:
    from .backend import SKILLS_BUILTIN_PATH_PREFIX, builtin_namespace

    return _Scope(prefix=SKILLS_BUILTIN_PATH_PREFIX, namespace=builtin_namespace())


def _personal_scope(account_id: str) -> _Scope:
    from .backend import SKILLS_PERSONAL_PATH_PREFIX, personal_namespace

    return _Scope(prefix=SKILLS_PERSONAL_PATH_PREFIX, namespace=personal_namespace(account_id))


def _inactive_personal_scope(account_id: str) -> _Scope:
    from .backend import SKILLS_INACTIVE_PERSONAL_PATH_PREFIX, inactive_personal_namespace

    return _Scope(
        prefix=SKILLS_INACTIVE_PERSONAL_PATH_PREFIX,
        namespace=inactive_personal_namespace(account_id),
    )


def _team_scope(team_id: str) -> _Scope:
    from .backend import SKILLS_TEAM_PATH_PREFIX, team_namespace

    return _Scope(prefix=SKILLS_TEAM_PATH_PREFIX, namespace=team_namespace(team_id))


def _store_backend(scope: _Scope) -> Any:
    """2026-08-26 수정 — 예전엔 `StoreBackend`를 절대경로(`scope.prefix`가
    붙은 `skill_md_path()` 결과)로 직접 썼는데, deepagents의 실제 규약은
    그 반대다: `StoreBackend`의 Store 키는 **route prefix가 이미 벗겨진
    상대경로**여야 한다(`CompositeBackend.write()`가 라우팅할 때 prefix를
    떼고 `"/"+나머지`만 하위 backend에 넘기는 것과 같은 규약 —
    `deepagents/backends/composite.py`의 `_route_for_path()` 실측 확인).

    이걸 어긴 채로 절대경로를 키로 그대로 썼더니, **실제 채팅 그래프가
    스킬을 읽을 때 쓰는 `CompositeBackend`(`SkillsMiddleware`가 이걸로
    `backend.ls(source_path)`를 부른다 — `source_path`는 라우트 prefix와
    정확히 같은 문자열)가 그 prefix를 완전히 벗기고 하위 backend에는 루트
    `"/"`만 물어봤다** — 그러면 `StoreBackend.ls("/")`가 저장된 키의 첫
    글자("/")만 벗겨서 첫 경로 조각(`"skills"`)을 마치 스킬 디렉터리인 것
    처럼 잘못 돌려줬다. 즉 **여태 등록된 개인/내장 스킬이 실제 채팅에서는
    단 하나도 안 보이고 있었다** — 설정 화면에 보이는 건 이 함수를 거치는
    REST 직접 조회(`list_personal_skills()` 등, prefix를 그대로 써서 우연히
    맞았다)일 뿐, 실제 `SkillsMiddleware` 스캔은 항상 빈 목록이었다(2026-08-26
    §8 하네스에서 재현·확인).

    고친 방식 — 여기서부터 `CompositeBackend`로 한 번 감싼다. 그러면 이
    모듈의 기존 호출부(`backend.write(skill_md_path(prefix,name), ...)`,
    `backend.ls(scope.prefix)` 등)는 절대경로를 그대로 써도 되고, 실제
    그래프가 쓰는 것과 **완전히 동일한 경로 변환**을 거치게 된다 — 쓰기와
    읽기가 서로 다른 규약을 쓰다가 어긋나는 일이 구조적으로 불가능해진다.
    """

    from deepagents.backends import CompositeBackend, StateBackend, StoreBackend

    from services.agent_runtime.memory.store import get_runtime_store

    inner = StoreBackend(namespace=lambda _rt: scope.namespace, store=get_runtime_store())
    return CompositeBackend(default=StateBackend(), routes={scope.prefix: inner})


#: `metadata.enabled`에 쓰는 값 — deepagents `_validate_metadata()`가
#: `dict[str, str]`로 강제 변환하므로(YAML 불리언을 그대로 두면 `str(True)`가
#: `"True"`가 돼 대문자 문제가 생긴다), 여기서부터 소문자 문자열로 직접 쓴다.
_ENABLED_TRUE = "true"
_ENABLED_FALSE = "false"

#: 개인 스킬을 팀에 공유하면 팀 namespace에 같은 SKILL.md를 한 건 만들되,
#: 누가 공유한 것인지 이 metadata로 남긴다. 팀원이 임의의 팀 스킬을 지우지
#: 못하고 자신이 공유한 것만 중지할 수 있게 하는 서버측 권한 근거다.
_SHARED_BY_ACCOUNT_ID = "shared_by_account_id"
_IMPORTED_FROM_TEAM_ID = "imported_from_team_id"
_IMPORTED_FROM_SKILL_NAME = "imported_from_skill_name"
_VALIDATION_RECEIPT_KEYS = (
    "validation_state", "validated_hash", "source_job_id", "source_revision",
    "runtime_profile_version", "tool_registry_version",
)


def _render_skill_md(
    *,
    name: str,
    description: str,
    body: str,
    enabled: bool = True,
    shared_by_account_id: str | None = None,
    imported_from_team_id: str | None = None,
    imported_from_skill_name: str | None = None,
    frontmatter: dict[str, Any] | None = None,
    validation_receipt: dict[str, Any] | None = None,
) -> str:
    updates = {
        _SHARED_BY_ACCOUNT_ID: shared_by_account_id,
        _IMPORTED_FROM_TEAM_ID: imported_from_team_id,
        _IMPORTED_FROM_SKILL_NAME: imported_from_skill_name,
    }
    if validation_receipt is not None:
        updates.update({key: validation_receipt.get(key) for key in _VALIDATION_RECEIPT_KEYS})
    return SkillDocument.create(
        name=name,
        description=description,
        body=body,
        frontmatter=frontmatter,
    ).updated(enabled=enabled, metadata_updates=updates).render()


def _parse_skill_md_details(
    content: str,
) -> tuple[str, str, str, bool, str | None, str | None, str | None]:
    """`---\\nyaml\\n---\\n\\nbody` 형식을 `(name, description, body, enabled)`로 나눈다.

    업로드 탭에서 쓴다 — 사람이 올리는 `.md` 파일은 이미 frontmatter를 담고
    있어서, 만들 때와 달리 **읽어서** 이름·설명을 꺼내야 한다(Claude의 스킬
    업로드가 파일 안 frontmatter에서 이름을 가져오는 것과 같은 방식,
    2026-08-22 확인). 여기서 나온 값은 그대로 `create_skill()`에 넘긴다 —
    저장 형식은 항상 이 모듈이 다시 만든 frontmatter 하나로 통일한다.

    `enabled`(2026-08-26)는 `metadata.enabled`가 명시적으로 `"false"`일
    때만 `False`다 — 이 필드가 없는 기존 스킬·업로드 파일은 전부 활성으로
    취급한다(하위 호환).
    """

    try:
        document = SkillDocument.parse(content)
    except ValueError as exc:
        logger.info("스킬 파일 frontmatter 파싱 실패", exc_info=exc)
        raise SkillError(
            "스킬 파일의 기본 정보 형식을 확인해 주세요. "
            "파일 맨 위에 name과 description을 올바른 YAML 형식으로 적어야 합니다."
        ) from exc
    metadata = document.metadata
    return (
        document.name,
        document.description,
        document.body,
        document.enabled,
        str(metadata.get(_SHARED_BY_ACCOUNT_ID) or "").strip() or None,
        str(metadata.get(_IMPORTED_FROM_TEAM_ID) or "").strip() or None,
        str(metadata.get(_IMPORTED_FROM_SKILL_NAME) or "").strip() or None,
    )


def parse_skill_md(content: str) -> tuple[str, str, str, bool]:
    """공개 호환 API. 공유 출처는 내부 상세 parser에서만 다룬다."""

    name, description, body, enabled, _shared_by, _imported_team, _imported_name = (
        _parse_skill_md_details(content)
    )
    return name, description, body, enabled


def _skill_response(
    *,
    skill_id: str,
    name: str,
    description: str,
    updated_at: str | None,
    enabled: bool = True,
    body: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "skill_id": skill_id,
        "name": name,
        "description": description,
        "updated_at": updated_at,
        "enabled": enabled,
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
        (
            _,
            description,
            body,
            enabled,
            shared_by_account_id,
            imported_from_team_id,
            imported_from_skill_name,
        ) = _parse_skill_md_details(file_data["content"])
    except SkillError:
        return None
    row = _skill_response(
        skill_id=name,
        name=name,
        description=description,
        updated_at=file_data.get("modified_at"),
        enabled=enabled,
        body=body if include_body else None,
    )
    row["shared_by_account_id"] = shared_by_account_id
    row["imported_from_team_id"] = imported_from_team_id
    row["imported_from_skill_name"] = imported_from_skill_name
    try:
        parsed = SkillDocument.parse(file_data["content"])
        row["frontmatter"] = parsed.frontmatter
        for key in _VALIDATION_RECEIPT_KEYS:
            row[key] = parsed.metadata.get(key)
    except ValueError:
        row["frontmatter"] = {"name": name, "description": description}
    return row


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


def create_skill(
    scope: _Scope,
    *,
    name: str,
    description: str,
    body: str,
    allow_reserved: bool = False,
    shared_by_account_id: str | None = None,
    imported_from_team_id: str | None = None,
    imported_from_skill_name: str | None = None,
    enabled: bool = True,
    frontmatter: dict[str, Any] | None = None,
    validation_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """한 namespace에 스킬을 새로 만든다. 같은 namespace의 이름만 유일하다.

    팀 스킬은 에이전트에 직접 합쳐지는 소스가 아니라 가져오기용 카탈로그이므로,
    팀과 개인에 같은 이름이 존재해도 서로 가리거나 충돌하지 않는다.
    """
    from .backend import skill_md_path

    name_error = validate_skill_name(name, allow_reserved=allow_reserved)
    if name_error:
        raise SkillError(name_error)
    _validate_description(description)
    _validate_body(body)

    backend = _store_backend(scope)
    path = skill_md_path(scope.prefix, name)
    if backend.read(path).error is None:
        raise SkillNameConflict(f"이미 '{name}' 이름의 스킬이 있습니다. 다른 이름을 써주세요.")
    content = _render_skill_md(
        name=name,
        description=description,
        body=body,
        enabled=enabled,
        shared_by_account_id=shared_by_account_id,
        imported_from_team_id=imported_from_team_id,
        imported_from_skill_name=imported_from_skill_name,
        frontmatter=frontmatter,
        validation_receipt=validation_receipt,
    )
    backend.write(path, content)
    return get_skill(scope, name)


def update_skill(
    scope: _Scope,
    name: str,
    *,
    description: str | None = None,
    body: str | None = None,
    enabled: bool | None = None,
    frontmatter: dict[str, Any] | None = None,
    validation_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """`enabled`가 없으면 유지한다. 개인 스킬의 실제 namespace 이동은
    `update_personal_skill()`이 담당하며, 이 함수는 한 scope 안의 내용 갱신만 한다.
    """
    from .backend import skill_md_path

    current = get_skill(scope, name)  # SkillNotFound가 여기서 난다.
    next_description = description if description is not None else current["description"]
    next_body = body if body is not None else current["body"]
    next_enabled = enabled if enabled is not None else current["enabled"]
    _validate_description(next_description)
    _validate_body(next_body)

    backend = _store_backend(scope)
    content = _render_skill_md(
        name=name,
        description=next_description,
        body=next_body,
        enabled=next_enabled,
        shared_by_account_id=current.get("shared_by_account_id"),
        imported_from_team_id=current.get("imported_from_team_id"),
        imported_from_skill_name=current.get("imported_from_skill_name"),
        frontmatter=frontmatter if frontmatter is not None else current.get("frontmatter"),
        validation_receipt=validation_receipt,
    )
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
    migrate_legacy_inactive_skills(account_id)
    rows = [*list_skills(_personal_scope(account_id)), *list_skills(_inactive_personal_scope(account_id))]
    rows.sort(key=lambda row: row["name"])
    return rows


def get_personal_skill(account_id: str, name: str) -> dict[str, Any]:
    migrate_legacy_inactive_skills(account_id)
    for scope in (_personal_scope(account_id), _inactive_personal_scope(account_id)):
        try:
            return get_skill(scope, name)
        except SkillNotFound:
            pass
    raise SkillNotFound("스킬을 찾을 수 없습니다.")


def create_personal_skill(
    account_id: str, *, team_id: str, name: str, description: str, body: str,
    enabled: bool = True, frontmatter: dict[str, Any] | None = None,
    validation_receipt: dict[str, Any] | None = None,
    imported_from_team_id: str | None = None,
    imported_from_skill_name: str | None = None,
) -> dict[str, Any]:
    """개인 스킬을 만든다.

    팀 스킬은 이제 에이전트가 직접 쓰는 상위 소스가 아니라 가져오기용
    카탈로그다. 같은 이름의 팀 항목이 있어도 개인 스킬을 가리지 않으므로
    예전의 `shadow_scope` 충돌 검사는 하지 않는다.
    """
    del team_id  # 호출 계약은 유지하되 이름 충돌 검사에는 더 이상 쓰지 않는다.
    migrate_legacy_inactive_skills(account_id)
    try:
        get_personal_skill(account_id, name)
    except SkillNotFound:
        pass
    else:
        raise SkillNameConflict(f"이미 '{name}' 이름의 스킬이 있습니다. 다른 이름을 써주세요.")
    scope = _personal_scope(account_id) if enabled else _inactive_personal_scope(account_id)
    from .versioning import increment_catalog_revision
    revision = increment_catalog_revision(account_id)
    receipt = dict(validation_receipt) if validation_receipt is not None else None
    if receipt is not None:
        receipt["source_revision"] = revision
    return create_skill(
        scope, name=name, description=description, body=body, enabled=enabled,
        frontmatter=frontmatter, validation_receipt=receipt,
        imported_from_team_id=imported_from_team_id,
        imported_from_skill_name=imported_from_skill_name,
    )


def update_personal_skill(
    account_id: str,
    name: str,
    *,
    description: str | None = None,
    body: str | None = None,
    enabled: bool | None = None,
    frontmatter: dict[str, Any] | None = None,
    validation_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    migrate_legacy_inactive_skills(account_id)
    source = _personal_scope(account_id)
    try:
        current = get_skill(source, name)
    except SkillNotFound:
        source = _inactive_personal_scope(account_id)
        current = get_skill(source, name)
    target_enabled = current["enabled"] if enabled is None else enabled
    target = _personal_scope(account_id) if target_enabled else _inactive_personal_scope(account_id)
    from .versioning import increment_catalog_revision
    revision = increment_catalog_revision(account_id)
    receipt = dict(validation_receipt) if validation_receipt is not None else None
    if receipt is not None:
        receipt["source_revision"] = revision
    if target == source:
        return update_skill(
            source,
            name,
            description=description,
            body=body,
            enabled=target_enabled,
            frontmatter=frontmatter,
            validation_receipt=receipt,
        )
    updated_document = SkillDocument.create(
        name=name,
        description=current["description"],
        body=current["body"],
        frontmatter=frontmatter if frontmatter is not None else current.get("frontmatter"),
    ).updated(
        description=description, body=body, enabled=target_enabled,
        metadata_updates=receipt or {},
    )
    backend = _store_backend(target)
    from .backend import skill_md_path
    target_path = skill_md_path(target.prefix, name)
    if backend.read(target_path).error is None:
        raise SkillNameConflict(f"대상 보관소에 이미 '{name}' 스킬이 있습니다.")
    backend.write(target_path, updated_document.render())
    delete_skill(source, name)
    return get_skill(target, name)


def delete_personal_skill(account_id: str, name: str) -> None:
    migrate_legacy_inactive_skills(account_id)
    for scope in (_personal_scope(account_id), _inactive_personal_scope(account_id)):
        try:
            delete_skill(scope, name)
            from .versioning import increment_catalog_revision
            increment_catalog_revision(account_id)
            return
        except SkillNotFound:
            pass
    raise SkillNotFound("스킬을 찾을 수 없습니다.")


def migrate_legacy_inactive_skills(account_id: str) -> int:
    """기존 활성 namespace의 ``metadata.enabled=false`` 파일을 한 번에 옮긴다."""
    from .backend import skill_md_path

    active = _personal_scope(account_id)
    inactive = _inactive_personal_scope(account_id)
    active_backend = _store_backend(active)
    inactive_backend = _store_backend(inactive)
    moved = 0
    for row in list_skills(active):
        if row["enabled"]:
            continue
        source_path = skill_md_path(active.prefix, row["name"])
        read = active_backend.read(source_path)
        if read.error:
            continue
        target_path = skill_md_path(inactive.prefix, row["name"])
        # 이전 이관이 write 뒤 delete 전에 중단됐다면 양쪽에 같은 이름이 남을
        # 수 있다. 비활성 보관소를 정본으로 두고 활성 쪽만 제거하면 재실행 가능하다.
        if inactive_backend.read(target_path).error is not None:
            inactive_backend.write(target_path, read.file_data["content"])
        active_backend.delete(source_path)
        moved += 1
    if moved:
        from .versioning import increment_catalog_revision
        increment_catalog_revision(account_id)
    return moved


def share_personal_skill(account_id: str, *, team_id: str, name: str) -> dict[str, Any]:
    """내 개인 스킬을 팀 namespace에 공유본으로 만든다.

    일반 팀 스킬 생성은 팀장만 가능하지만, 이 경로는 사용자가 **자기 개인
    스킬 한 건**만 같은 팀에 공유한다. 원본 소유권과 공유자 metadata를 서버가
    확인하므로 다른 사람의 내용을 팀에 올리는 우회 경로가 되지 않는다.
    """

    personal = get_personal_skill(account_id, name)
    if personal.get("imported_from_team_id"):
        raise SkillPermissionDenied(
            "팀 스킬에서 가져온 스킬은 다시 팀에 공유할 수 없습니다."
        )
    from .versioning import validation_hash
    if (
        personal.get("validation_state") != "VERIFIED"
        or personal.get("validated_hash") != validation_hash(personal)
    ):
        raise SkillError("검증을 통과한 스킬만 팀에 공유할 수 있습니다.")
    receipt = {key: personal.get(key) for key in _VALIDATION_RECEIPT_KEYS}
    return create_skill(
        _team_scope(team_id),
        name=personal["name"],
        description=personal["description"],
        body=personal["body"],
        shared_by_account_id=account_id,
        frontmatter=personal.get("frontmatter"),
        # 팀 카탈로그에는 활성/비활성 개념이 없다. 공유 당시 개인 상태와
        # 무관하게 다른 팀원이 내용을 보고 가져올 수 있어야 한다.
        enabled=True,
        validation_receipt=receipt,
    )


def import_team_skill(account_id: str, *, team_id: str, name: str) -> dict[str, Any]:
    """팀 카탈로그의 스킬을 독립적인 개인 사본으로 가져온다.

    **가져올 때 다시 검증하지 않는다**(2026-08-30 결정). 팀 카탈로그에는
    검증을 통과한 스킬만 올라온다(`share_personal_skill`가 `VERIFIED`만
    허용) — 이미 검증이 끝난 내용을 그대로 개인 공간으로 복사할 뿐이므로,
    일반 등록과 같은 검증 job을 만들 이유가 없다. 공유본의 검증 영수증도
    그대로 옮겨 개인 사본이 검증 상태를 유지하게 한다.

    이후 원 공유자의 비활성화·수정·공유 중지나 팀장의 카탈로그 삭제는 이
    개인 사본에 영향을 주지 않는다. 같은 이름의 개인 스킬이 이미 있으면
    조용히 덮어쓰지 않고 기존 이름 충돌 규칙으로 거부한다.
    """

    shared = get_team_skill(team_id, name)
    receipt = {key: shared.get(key) for key in _VALIDATION_RECEIPT_KEYS}
    return {
        "requires_validation": False,
        "skill": create_personal_skill(
            account_id, team_id=team_id, name=shared["name"],
            description=shared["description"], body=shared["body"], enabled=True,
            frontmatter=shared.get("frontmatter"), validation_receipt=receipt,
            imported_from_team_id=team_id, imported_from_skill_name=name,
        ),
    }


def stop_sharing_personal_skill(account_id: str, *, team_id: str, name: str) -> None:
    """자신이 만든 팀 공유본만 제거한다. 개인 원본은 건드리지 않는다."""

    team_skill = get_team_skill(team_id, name)
    if team_skill.get("shared_by_account_id") != account_id:
        raise SkillPermissionDenied("내가 공유한 스킬만 공유를 중지할 수 있습니다.")
    delete_skill(_team_scope(team_id), name)


def update_personal_skill_and_shared_copy(
    account_id: str,
    *,
    team_id: str,
    name: str,
    description: str | None = None,
    body: str | None = None,
    enabled: bool | None = None,
    frontmatter: dict[str, Any] | None = None,
    validation_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """개인 원본을 고치고, 내가 공유 중인 팀 사본도 같은 내용으로 맞춘다."""

    updated = update_personal_skill(
        account_id,
        name,
        description=description,
        body=body,
        enabled=enabled,
        frontmatter=frontmatter,
        validation_receipt=validation_receipt,
    )
    try:
        team_skill = get_team_skill(team_id, name)
    except SkillNotFound:
        return updated
    if team_skill.get("shared_by_account_id") == account_id:
        update_skill(
            _team_scope(team_id),
            name,
            description=updated["description"],
            body=updated["body"],
            validation_receipt={key: updated.get(key) for key in _VALIDATION_RECEIPT_KEYS},
            # 팀 카탈로그에는 활성/비활성 상태가 없다. 개인 토글은 공유본과
            # 이미 가져간 다른 팀원의 개인 사본에 영향을 주지 않는다.
        )
    return updated


def delete_personal_skill_and_shared_copy(account_id: str, *, team_id: str, name: str) -> None:
    """개인 원본 삭제 시 자신이 만든 팀 공유본도 함께 정리한다."""

    try:
        team_skill = get_team_skill(team_id, name)
    except SkillNotFound:
        team_skill = None
    if team_skill is not None and team_skill.get("shared_by_account_id") == account_id:
        delete_skill(_team_scope(team_id), name)
    delete_personal_skill(account_id, name)


# ---------------------------------------------------------------------------
# 팀 스킬 — 조회는 팀원 전체, 쓰기(생성·수정·삭제)는 leader만
# (`2026-08-20_16_Skill_Middleware_설계.md` "팀 스킬" 절 — 팀원이 팀 스킬로
# 등록해달라고 하는 경로 자체가 없다).
# ---------------------------------------------------------------------------


def _require_leader(actor_role: str) -> None:
    if actor_role != "leader":
        raise SkillPermissionDenied("팀 스킬은 팀장만 만들고 고치고 지울 수 있습니다.")


def list_team_skills(team_id: str) -> list[dict[str, Any]]:
    _mark_legacy_team_skills(team_id)
    return list_skills(_team_scope(team_id))


def get_team_skill(team_id: str, name: str) -> dict[str, Any]:
    row = get_skill(_team_scope(team_id), name)
    if not row.get("validation_state"):
        row = update_skill(
            _team_scope(team_id), name,
            validation_receipt={"validation_state": "LEGACY_UNVERIFIED"},
        )
    return row


def _mark_legacy_team_skills(team_id: str) -> None:
    """영수증 도입 전에 저장된 팀 카탈로그 항목을 명시적으로 표시한다."""

    scope = _team_scope(team_id)
    for row in list_skills(scope):
        if not row.get("validation_state"):
            update_skill(
                scope, row["name"],
                validation_receipt={"validation_state": "LEGACY_UNVERIFIED"},
            )


def delete_team_skill(team_id: str, name: str, *, actor_role: str) -> None:
    _require_leader(actor_role)
    delete_skill(_team_scope(team_id), name)


# ---------------------------------------------------------------------------
# 내장 스킬 — 계정·팀과 무관하게 항상 존재한다(2026-08-24, skill-creator).
# 쓰기는 `ensure_builtin_skill_creator()`(아래) 하나뿐이고, 사람이 직접
# 만들고·고치고·지우는 경로는 없다 — `validate_skill_name()`이 예약된
# 이름을 개인/팀 생성에서 막는 것과 짝이다.
# ---------------------------------------------------------------------------


def list_builtin_skills() -> list[dict[str, Any]]:
    return list_skills(_builtin_scope())


def get_builtin_skill(name: str) -> dict[str, Any]:
    return get_skill(_builtin_scope(), name)


#: 이 프로세스에서 이미 한 번 확인했으면 다시 DB를 안 본다(2026-08-24).
#: `bootstrap.py`의 "호출마다 새로 조립하지만 I/O는 실제 필요할 때만"
#: 원칙과 같은 이유 — 매 채팅 턴마다 존재 확인 쓰기를 반복할 필요는 없다.
#: 여러 워커 프로세스가 각자 한 번씩 확인하는 것은 안전하다(아래 `create_skill`
#: 호출이 이미 있으면 `SkillNameConflict`로 조용히 넘어간다).
_builtin_skill_creator_seeded = False


def ensure_builtin_skill_creator() -> None:
    """`skill-creator` 내장 스킬을 `builtin_content.py`의 현재 상수 값으로 맞춘다.

    **2026-08-24 수정 — "없으면 만든다"에서 "항상 최신 내용으로 맞춘다"로
    바꿨다.** 이 스킬 본문은 사람이 직접 고칠 방법이 없다(위 섹션 docstring
    — 쓰기는 이 함수 하나뿐). 그러니 내용을 바꾸는 유일한 방법은
    `builtin_content.py`의 상수를 고치고 서버를 재시작하는 것인데, 예전
    "이미 있으면 그대로 둔다" 버전은 그렇게 고쳐도 이미 씌운 DB 내용이
    안 바뀌어서 고친 게 반영이 안 됐다(실제로 겪음 — 질문 문구를 짧게
    고쳤는데 배포해도 그대로였다). 현재 저장된 내용이 상수와 다를 때만
    `update_skill()`을 부른다 — 매번 무조건 쓰기를 내지는 않는다.
    """

    global _builtin_skill_creator_seeded
    if _builtin_skill_creator_seeded:
        return

    from .builtin_content import SKILL_CREATOR_BODY, SKILL_CREATOR_DESCRIPTION, SKILL_CREATOR_NAME

    scope = _builtin_scope()
    try:
        current = get_skill(scope, SKILL_CREATOR_NAME)
    except SkillNotFound:
        current = None

    if current is None:
        try:
            create_skill(
                scope,
                name=SKILL_CREATOR_NAME,
                description=SKILL_CREATOR_DESCRIPTION,
                body=SKILL_CREATOR_BODY,
                allow_reserved=True,
            )
        except SkillNameConflict:
            pass  # 다른 워커가 그 사이 먼저 만들었다 — 그대로 둔다.
    elif current["description"] != SKILL_CREATOR_DESCRIPTION or current["body"] != SKILL_CREATOR_BODY:
        update_skill(scope, SKILL_CREATOR_NAME, description=SKILL_CREATOR_DESCRIPTION, body=SKILL_CREATOR_BODY)

    _builtin_skill_creator_seeded = True


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
    "update_personal_skill_and_shared_copy",
    "delete_personal_skill",
    "delete_personal_skill_and_shared_copy",
    "share_personal_skill",
    "import_team_skill",
    "stop_sharing_personal_skill",
    "list_team_skills",
    "get_team_skill",
    "delete_team_skill",
    "list_builtin_skills",
    "get_builtin_skill",
    "ensure_builtin_skill_creator",
]
