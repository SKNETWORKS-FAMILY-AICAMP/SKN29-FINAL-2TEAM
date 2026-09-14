"""LangGraph Checkpointer(`PostgresSaver`) — 프로세스당 한 번만 연결한다.

`memory/store.py`와 같은 패턴. 락 없이 이중 검사만 하면 동시 요청이 겹칠 때
연결이 중복 생성되고 `.setup()` DDL도 겹쳐 500 에러가 날 수 있다
(2026-08-22 `memory/store.py`에서 실제로 겪은 사례) — 같은 락으로 막는다.

끊긴 연결은 버리고 다시 연다 — 이유는 `memory/store.py` 모듈 docstring
(2026-09-14 운영 장애)에 있다.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres import PostgresSaver

logger = logging.getLogger(__name__)

_checkpointer: Any = None
_checkpointer_cm: Any = None
_checkpointer_lock = threading.Lock()


def _usable(checkpointer: Any) -> bool:
    """쥐고 있는 연결이 살아 있는가. psycopg 가 끊긴 연결을 `closed`/`broken` 으로 알린다."""
    conn = getattr(checkpointer, "conn", None)
    return not (getattr(conn, "closed", False) or getattr(conn, "broken", False))


def get_checkpointer() -> "PostgresSaver":
    """프로세스 전역 `PostgresSaver`. 최초 호출에서만 연결하고 스키마를 만든다."""
    global _checkpointer, _checkpointer_cm
    if _checkpointer is not None and _usable(_checkpointer):
        return _checkpointer

    with _checkpointer_lock:
        if _checkpointer is not None:  # 락 대기 중 다른 스레드가 만들었을 수 있다
            if _usable(_checkpointer):
                return _checkpointer
            logger.warning("Checkpointer 연결이 끊겨 다시 연결합니다")
            try:
                _checkpointer_cm.__exit__(None, None, None)
            except Exception:  # noqa: BLE001 - 이미 끊긴 연결을 닫다 나는 오류는 의미가 없다
                pass
            _checkpointer = None
            _checkpointer_cm = None

        from django.conf import settings
        from langgraph.checkpoint.postgres import PostgresSaver

        _checkpointer_cm = PostgresSaver.from_conn_string(settings.RAW_DATABASE_URL)
        _checkpointer = _checkpointer_cm.__enter__()
        _checkpointer.setup()  # 멱등 — 이미 있으면 아무 것도 안 함
        return _checkpointer


__all__ = ["get_checkpointer"]
