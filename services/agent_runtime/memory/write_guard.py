"""`/memories/users/` 쓰기 전, 코드로 형태 판단이 가능한 내용만 막는다.

정본: `2026-08-19_02_메모리_기본에이전트_분리_및_쓰기_방어_설계.md` §2,
`2026-08-19_04_write_guard_구현설계.md`

**여기서 하는 일과 안 하는 일.** credential/개인정보/권한·보안 서술 셋만 본다 —
값의 "형태"만으로 판단 가능한 카테고리다. "모델이 추론한 사실인가", "이
프로젝트에만 해당하는가" 같은 맥락 판단은 `memory/backend.py`의
`_MEMORY_ROUTING_PROMPT`가 맡는다. 이 미들웨어는 그 안내가 뚫렸을 때의 마지막
안전망이지 저장 판단 전체를 대신하지 않는다.

**한계**(`2026-08-19_04` §4): 여러 번의 `edit_file`로 쪼개 넣으면 각 호출은
통과할 수 있다 — 완전한 방어가 아니라 명백한 경우를 잡는 안전망이다. 전화번호
패턴은 정당한 요청("이 번호로 리마인더 보내줘")도 걸린다. 권한/보안 키워드는
문맥 없이 문자열 포함 여부만 본다 — 진위와 무관하게 카테고리째 막는 의도된
선택이다.

패턴 정의 자체는 `sensitive_text.py`에 있다. `apps/chat/api_views.py`의 채팅
입력 마스킹도 같은 패턴을 쓰므로, 두 기능이 "무엇을 민감정보로 보는가"에 대해
다른 정의를 갖지 않도록 여기서 중복 정의하지 않는다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from deepagents.backends.utils import validate_path
from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage

from services.agent_runtime.memory.backend import MEMORY_USERS_PATH_PREFIX
from services.agent_runtime.sensitive_text import CATEGORY_LABELS, match_category

if TYPE_CHECKING:
    from collections.abc import Callable

    from langchain.agents.middleware.types import ToolCallRequest

#: 검사 대상 도구. `read_file`/`ls` 등 조회 도구는 애초에 아무것도 안 쓰므로
#: 대상이 아니다.
_GUARDED_TOOLS = {"write_file", "edit_file"}


class MemoryWriteGuardMiddleware(AgentMiddleware):
    """`/memories/users/` 쓰기 전, 코드로 형태 판단이 가능한 세 카테고리만
    검사한다. 모듈 docstring 참고.

    Root에만 붙인다 — Child는 진짜 `StoreBackend`가 없어(빈 `StateBackend`로
    떨어진다) `/memories/users/`에 써도 저장이 안 되므로 막을 대상이 없다.
    `MiddlewareFactory.build()`의 `custom_middleware`는 Root/Child가 공유하므로
    거기 넣으면 안 되고, `factory.py`의 Root 분기에서만 배선한다.
    """

    def __init__(self, *, guarded_prefix: str = MEMORY_USERS_PATH_PREFIX) -> None:
        super().__init__()
        self._guarded_prefix = guarded_prefix

    def wrap_tool_call(
        self, request: "ToolCallRequest", handler: "Callable[[ToolCallRequest], Any]"
    ) -> Any:
        name = request.tool_call["name"]
        if name not in _GUARDED_TOOLS:
            return handler(request)

        args = request.tool_call["args"]
        raw_path = args.get("file_path", "")
        try:
            # `wrap_tool_call`은 도구 본문 실행 전에 끼어든다 — 여기서 보는
            # `file_path`는 모델이 보낸 그대로의, 아직 정규화 전 문자열이다.
            # 도구 본문과 같은 정규화 함수를 재사용해야 표기만 다르고 실제로는
            # `/memories/users/`로 떨어지는 경로(`"memories/users/..."`,
            # `"/memories//users/..."` 등)를 놓치지 않는다
            # (`2026-08-19_04_write_guard_구현설계.md` §2).
            normalized_path = validate_path(raw_path)
        except ValueError:
            # 경로 자체가 무효하면 write_guard의 관심사가 아니다 — 도구
            # 본문이 어차피 같은 오류를 낼 것이므로 그대로 넘긴다.
            return handler(request)

        if not normalized_path.startswith(self._guarded_prefix):
            return handler(request)

        text_to_check = args.get("content", "") if name == "write_file" else args.get("new_string", "")
        category = match_category(text_to_check)
        if category is None:
            return handler(request)

        # 매칭된 원문(비밀번호·주민번호 값 자체)은 오류 메시지에 절대 옮기지
        # 않는다 — ToolMessage는 대화 기록에 그대로 남으므로, 여기 원문을
        # 넣으면 "저장은 막았지만 대화 로그에는 남는" 모순이 생긴다. 카테고리
        # 이름만 알려준다.
        return ToolMessage(
            content=(
                f"이 내용은 저장하지 않았습니다 — {CATEGORY_LABELS[category]}"
                "이(가) 포함된 것으로 보입니다. 개인 장기 메모리에는 "
                "credential·개인정보·권한/보안 관련 서술을 저장하지 않습니다. "
                "다른 방식으로 표현해서 다시 시도할 수 있습니다."
            ),
            tool_call_id=request.tool_call["id"],
            name=name,
            status="error",
        )


def build_memory_write_guard(
    *, guarded_prefix: str = MEMORY_USERS_PATH_PREFIX
) -> MemoryWriteGuardMiddleware:
    return MemoryWriteGuardMiddleware(guarded_prefix=guarded_prefix)


__all__ = ["MemoryWriteGuardMiddleware", "build_memory_write_guard"]
