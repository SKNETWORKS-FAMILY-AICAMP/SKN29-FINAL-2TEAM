"""§8.10 "스킬 경쟁 환경" — 후보 스킬 하나만 놓고 테스트하면 정확도가 부풀려진다.

정본: 03_스킬_검증_등록_설계.md §8.10. 검증 시작 시점의 활성 개인 스킬을
distractor로, 내장 스킬은 그대로, 후보 초안만 새로 얹은 **완전히 격리된**
인메모리 Store를 만든다 — 실제 개인 Store와 외부 시스템은 건드리지 않는다.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from langgraph.store.memory import InMemoryStore

if TYPE_CHECKING:
    from deepagents.backends import StoreBackend

EVAL_CANDIDATE_PATH_PREFIX = "/skills/eval/candidate/"
EVAL_DISTRACTOR_PATH_PREFIX = "/skills/eval/distractors/"


def _eval_builtin_namespace() -> tuple[str, str]:
    return ("skill", "builtin")


def _eval_candidate_namespace() -> tuple[str, str]:
    return ("skill", "eval-candidate")


def _eval_distractor_namespace() -> tuple[str, str]:
    return ("skill", "eval-distractor")


@dataclass(frozen=True)
class EphemeralSkillSnapshot:
    store: InMemoryStore
    candidate_snapshot_hash: str
    distractor_snapshot_hashes: dict[str, str]


def _write_skill(store: InMemoryStore, *, namespace: tuple[str, ...], name: str, content: str) -> None:
    """2026-08-26 수정 — 예전엔 `prefix` 인자를 받아 `skill_md_path(prefix,
    name)`(절대경로)를 키로 썼다. `StoreBackend`에 절대경로(`skill_md_path
    (prefix, name)`)를 키로 직접 쓰면 안 된다 — `CompositeBackend`(실제
    그래프가 `SkillsMiddleware`를 통해 이 store를 읽을 때 쓴다)는 경로가
    라우트 prefix와 정확히 같을 때 그 prefix를 통째로 벗기고 하위 backend엔
    루트 `"/"`만 물어본다(`deepagents/backends/composite.py::_route_for_path()`
    실측 확인). 절대경로를 키로 쓰면 `StoreBackend.ls("/")`가 저장된 키의
    첫 경로 조각(`"skills"`)을 스킬 디렉터리로 착각해 잘못된 경로를
    돌려준다 — 그 결과 이 하네스가 만든 store는 후보든 distractor든 내장
    사본이든 **모델에게 단 하나도 안 보였다**(2026-08-26 발견·재현).
    `service.py::_store_backend()`와 같은 원인이라 같은 날 함께 고쳤다.

    고친 방식 — 여기서는 `CompositeBackend`를 새로 씌우는 대신, 애초에
    prefix가 없는 **네임스페이스-상대 경로**로 직접 쓴다. 이 store는
    `EvalSkillsProvider.routes()`가 그대로 `CompositeBackend`의 route로
    등록하므로(운영 코드의 `skill_routes()`와 동일한 패턴), 그래프가
    `ls(prefix)`/`read(prefix+...)`로 물어보면 Composite가 prefix를 벗기고
    이 상대경로 키를 찾는다 — 쓰기·읽기가 같은 규약을 쓰게 된다.
    """

    from deepagents.backends import StoreBackend

    backend: "StoreBackend" = StoreBackend(namespace=lambda _rt: namespace, store=store)
    backend.write(f"/{name}/SKILL.md", content)


def build_ephemeral_skill_store(
    *,
    candidate_document: dict[str, Any],
    distractor_documents: list[dict[str, Any]],
) -> EphemeralSkillSnapshot:
    """후보+distractor+내장을 담은 새 인메모리 Store를 만든다.

    `candidate_document`/`distractor_documents`는 `SkillDocument`가 아니라
    이미 `service.py`의 `_render_skill_md()`가 만든 **완성된 SKILL.md
    텍스트**를 담은 `{"name": ..., "content": ...}` 형태다 — 렌더링 규칙을
    이 모듈에서 다시 만들지 않는다(같은 이유로 `service.py`의
    `_store_backend()`처럼 진짜 `StoreBackend`를 그대로 재사용한다, 아래
    `_write_skill`).
    """

    store = InMemoryStore()

    # 내장 스킬 — 실제 프로덕션 Store에서 그대로 복사한다. 읽기 전용으로
    # 쓰지만(§8.10 "내장 스킬은 실제 내장 source를 읽기 전용으로 사용"),
    # 이 store 자체가 실행마다 새로 만드는 사본이라 실수로 써도 실제
    # 내장 스킬에는 영향이 없다.
    from services.agent_runtime.skills.service import _render_skill_md, get_builtin_skill, list_builtin_skills

    for row in list_builtin_skills():
        full = get_builtin_skill(row["name"])
        content = _render_skill_md(
            name=full["name"], description=full["description"], body=full["body"],
            frontmatter=full.get("frontmatter"),
        )
        _write_skill(
            store,
            namespace=_eval_builtin_namespace(),
            name=full["name"],
            content=content,
        )

    _write_skill(
        store,
        namespace=_eval_candidate_namespace(),
        name=candidate_document["name"],
        content=candidate_document["content"],
    )
    candidate_hash = hashlib.sha256(candidate_document["content"].encode("utf-8")).hexdigest()

    distractor_hashes: dict[str, str] = {}
    for doc in distractor_documents:
        _write_skill(
            store,
            namespace=_eval_distractor_namespace(),
            name=doc["name"],
            content=doc["content"],
        )
        distractor_hashes[doc["name"]] = hashlib.sha256(doc["content"].encode("utf-8")).hexdigest()

    return EphemeralSkillSnapshot(
        store=store, candidate_snapshot_hash=candidate_hash, distractor_snapshot_hashes=distractor_hashes
    )


class EvalSkillsProvider:
    """`SkillsProvider`(services/agent_runtime/skills/provider.py)와 같은
    얇은 파사드 인터페이스 — `AgentRuntimeFactory`가 실제와 구분하지 않고
    받아 쓴다."""

    def __init__(self, snapshot: EphemeralSkillSnapshot) -> None:
        self._snapshot = snapshot

    def sources(self) -> list[str]:
        return ["/skills/builtin/", EVAL_CANDIDATE_PATH_PREFIX, EVAL_DISTRACTOR_PATH_PREFIX]

    def routes(self, *, account_id: str, team_id: str) -> dict[str, "StoreBackend"]:  # noqa: ARG002
        from deepagents.backends import StoreBackend

        store = self._snapshot.store
        return {
            "/skills/builtin/": StoreBackend(
                namespace=lambda _rt: _eval_builtin_namespace(), store=store
            ),
            EVAL_CANDIDATE_PATH_PREFIX: StoreBackend(
                namespace=lambda _rt: _eval_candidate_namespace(), store=store
            ),
            EVAL_DISTRACTOR_PATH_PREFIX: StoreBackend(
                namespace=lambda _rt: _eval_distractor_namespace(), store=store
            ),
        }

    def system_prompt(self) -> str:
        # 실제 production 프롬프트를 그대로 재사용한다(§8.10 "평가 전용 프롬프트로
        # '후보를 반드시 사용하라'고 힌트를 주지 않는다") — 검증 대상이 바로 이
        # 프롬프트로 실제 상황에서 후보를 고르는지이므로, 검증 자체가 다른
        # 프롬프트를 쓰면 결과가 production과 어긋난다.
        from services.agent_runtime.skills.backend import skills_system_prompt

        return skills_system_prompt()

    def store(self) -> InMemoryStore:
        return self._snapshot.store


__all__ = [
    "EphemeralSkillSnapshot",
    "EvalSkillsProvider",
    "build_ephemeral_skill_store",
    "EVAL_CANDIDATE_PATH_PREFIX",
    "EVAL_DISTRACTOR_PATH_PREFIX",
]
