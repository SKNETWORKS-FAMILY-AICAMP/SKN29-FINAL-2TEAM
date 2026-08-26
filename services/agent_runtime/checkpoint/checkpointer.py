"""LangGraph Checkpointer(`PostgresSaver`) — 프로세스당 한 번만 연결한다.

`memory/store.py`와 같은 패턴. 락 없이 이중 검사만 하면 동시 요청이 겹칠 때
연결이 중복 생성되고 `.setup()` DDL도 겹쳐 500 에러가 날 수 있다
(2026-08-22 `memory/store.py`에서 실제로 겪은 사례) — 같은 락으로 막는다.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres import PostgresSaver

_checkpointer: Any = None
_checkpointer_cm: Any = None
_checkpointer_lock = threading.Lock()


def get_checkpointer() -> "PostgresSaver":
    """프로세스 전역 `PostgresSaver`. 최초 호출에서만 연결하고 스키마를 만든다."""
    global _checkpointer, _checkpointer_cm
    if _checkpointer is not None:
        return _checkpointer

    with _checkpointer_lock:
        if _checkpointer is not None:  # 락 대기 중 다른 스레드가 만들었을 수 있다
            return _checkpointer

        from django.conf import settings
        from langgraph.checkpoint.postgres import PostgresSaver

        _checkpointer_cm = PostgresSaver.from_conn_string(settings.RAW_DATABASE_URL)
        _checkpointer = _checkpointer_cm.__enter__()
        _checkpointer.setup()  # 멱등 — 이미 있으면 아무 것도 안 함
        return _checkpointer


__all__ = ["get_checkpointer"]
