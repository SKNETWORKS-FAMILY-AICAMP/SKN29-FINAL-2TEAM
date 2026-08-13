"""Deep Agent 실행 전후에 공통 정책을 삽입하는 확장 영역.

MVP 상태: 비활성. build()는 항상 빈 리스트를 반환한다 — 이게 Deep Agents 자체의
기본 Middleware를 제거한다는 뜻은 아니다(02 §11). 서비스 전용 커스텀
Middleware(권한 검사·HITL)가 아직 없다는 뜻일 뿐이다.

도입 조건: 02 §2 원칙 8 — "서비스 전용 커스텀 Middleware, Memory, TODO,
Checkpointer는 MVP에서 비활성화한다."가 팀 결정으로 뒤집힐 때.
"""

from services.agent_runtime.middleware.factory import MiddlewareFactory

__all__ = ["MiddlewareFactory"]
