"""`skill_register` 성공 직후 `state["skills_metadata"]`를 다시 갱신한다.

deepagents의 `SkillsMiddleware.before_agent()`는 스킬 목록을 **세션당 한
번만** 스캔한다 — 이미 `skills_metadata`가 state에 있으면(같은 체크포인트
세션의 이전 턴에서 이미 읽었으면) 다시 안 읽는다(`deepagents/middleware/
skills.py` 실측). 그래서 세션 도중 `skill_register`로 새 스킬을 만들어도,
자동으로 뜨는 "사용 가능한 스킬" 목록에는 다음 세션이 될 때까지 안
나타났다.

메모리와 이유가 다르다. 메모리가 세션 내내 스냅샷을 고정하는 건 Anthropic
프롬프트 캐싱 경계(`add_cache_control`)를 살리기 위해서인데, 스킬 블록에는
애초에 그 캐시 경계가 안 걸려 있다(`SkillsMiddleware` 생성자에 그 옵션
자체가 없다) — 그러니 스킬은 고정해서 얻는 이득이 없고, 새로 만든 스킬을
같은 세션에서 못 쓰는 손해만 남는다. 그래서 스킬은 쓰기 직후 바로 갱신한다.

**전체 소스를 다시 스캔하지 않는다.** `before_agent()`처럼 소스마다
`ls()` + 그 소스의 스킬 전부를 `download_files()`로 다시 받으면, 등록 한
건마다 비용이 "이미 등록된 스킬 전체 개수"에 비례해서 커진다. 대신 방금
쓴 스킬 하나만 정확히 짚어서(`scope`/`name`으로 경로가 결정적으로 정해짐)
`download_files()`를 한 번만 부르고, 기존 캐시에 그 항목 하나만 얹는다.

팀 스킬은 가져오기용 카탈로그라 에이전트 스킬 목록에 직접 들어가지 않는다.
개인 스킬 등록만 방금 쓴 개인 경로를 읽어 현재 세션 캐시에 합친다. 팀과
개인은 서로 다른 역할이라 같은 이름이어도 에이전트 목록에서 충돌하지 않는다.

Root에만 붙는다 — Child는 스킬 backend가 없다(`factory.py`의 4-6 분기).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.types import Command

if TYPE_CHECKING:
    from collections.abc import Callable

    from deepagents.backends import BackendProtocol
    from langchain.agents.middleware.types import ToolCallRequest

logger = logging.getLogger(__name__)

#: 대상 도구. 스킬을 쓰는 도구는 지금 이것 하나뿐이다(수정·삭제는 채팅
#: 도구가 아니라 설정 화면 REST API 경로라 이 미들웨어의 대상이 아니다).
_GUARDED_TOOLS = {"skill_register"}

#: `scope` 인자 → 경로 접두어. `skill_register`(services/harness/registry.py의
#: `_skill_register`)가 받는 값과 정확히 같아야 한다.
_SCOPE_TO_PREFIX = {
    "PERSONAL": "/skills/personal/",
}


class SkillRegisterSyncMiddleware(AgentMiddleware):
    """`skill_register` 성공 직후, 방금 쓴 스킬 하나만 다시 읽어 `skills_metadata`에 얹는다."""

    def __init__(self, *, backend: "BackendProtocol") -> None:
        super().__init__()
        self._backend = backend

    def wrap_tool_call(
        self, request: "ToolCallRequest", handler: "Callable[[ToolCallRequest], Any]"
    ) -> Any:
        name = request.tool_call["name"]
        if name not in _GUARDED_TOOLS:
            return handler(request)

        result = handler(request)

        if isinstance(result, ToolMessage) and result.status == "error":
            # 등록이 거부됐다(이름 충돌·권한 없음 등) — 갱신할 게 없다.
            return result

        args = request.tool_call["args"]
        prefix = _SCOPE_TO_PREFIX.get(args.get("scope"))
        skill_name = args.get("name")
        if args.get("scope") == "TEAM":
            # 팀 스킬은 가져오기용 카탈로그다. 등록은 성공했지만 현재
            # 에이전트의 skills_metadata에는 직접 추가하지 않는다.
            return result
        if prefix is None or not skill_name:
            # 방어적 분기 — `_skill_register`가 이미 scope/name을 검증해서
            # 실제로는 여기 안 걸린다. 걸리더라도 목록 갱신만 건너뛸 뿐,
            # 방금 쓴 스킬 자체는 이미 저장됐으니 다음 세션엔 정상적으로 보인다.
            logger.warning("skill_register 결과에서 scope/name을 못 읽어 목록 갱신을 건너뜀")
            return result

        skill_dir_path = f"{prefix}{skill_name}"
        skill_md_path = f"{skill_dir_path}/SKILL.md"

        # 지연 import — deepagents.middleware.skills는 deepagents 전체를
        # 끌고 들어온다. `_skill_metadata_from_response`는 private 함수지만,
        # SKILL.md 프런트매터 파싱을 다시 구현하지 않고 라이브러리 것을
        # 그대로 재사용한다 — deepagents가 파싱 로직을 바꾸면 여기도 자동으로
        # 같이 맞는다.
        from deepagents.middleware.skills import _skill_metadata_from_response

        [response] = self._backend.download_files([skill_md_path])
        new_skill = _skill_metadata_from_response(response, skill_dir_path, skill_md_path)
        if new_skill is None:
            logger.warning("방금 등록한 스킬을 다시 읽지 못해 목록 갱신을 건너뜀: %s", skill_md_path)
            return result

        current = {skill["name"]: skill for skill in request.state.get("skills_metadata", [])}
        current[new_skill["name"]] = new_skill

        return Command(update={"skills_metadata": list(current.values()), "messages": [result]})


def build_skill_register_sync(*, backend: "BackendProtocol") -> SkillRegisterSyncMiddleware:
    return SkillRegisterSyncMiddleware(backend=backend)


__all__ = ["SkillRegisterSyncMiddleware", "build_skill_register_sync"]
