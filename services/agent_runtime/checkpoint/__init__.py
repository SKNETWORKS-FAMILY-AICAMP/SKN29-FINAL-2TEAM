"""실행 중단·재개, 턴 간 상태 유지를 위한 Checkpointer — `PostgresSaver`.

2026-08-18, §5 Phase 1로 착수(`2026-08-13_04_작업자B_실행코어_세부계획.md` §5 Phase 1).
`memory/store.py`와 같은 프로세스 전역 싱글턴 패턴을 그대로 따른다 — `checkpointer.py`
docstring 참고.
"""

from services.agent_runtime.checkpoint.checkpointer import get_checkpointer
from services.agent_runtime.checkpoint.provider import CheckpointerProvider

__all__ = ["CheckpointerProvider", "get_checkpointer"]
