"""설정과 실행 문맥에 맞는 Middleware 목록을 조립한다.

MVP: 항상 빈 리스트. factory.py(AgentRuntimeFactory)가 이 확장 지점을 항상
거치는 형태는 유지하되, 실제 커스텀 Middleware가 생기기 전까지는 아무 동작도
하지 않는다(01 §8.3).
"""

from __future__ import annotations

from typing import Any


class MiddlewareFactory:
    def build(self, *, definition: Any, context: Any) -> list:
        return []
