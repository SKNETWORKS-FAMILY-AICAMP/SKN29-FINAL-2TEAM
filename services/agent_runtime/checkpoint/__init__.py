"""실행 상태 저장과 중단 후 재개를 담당할 확장 영역.

MVP 상태: 비활성. build()는 항상 None을 반환한다(01 §8.3). 대화 기억은 지금처럼
저장된 메시지 히스토리를 다시 주입하는 방식으로 시작하고(01 §13), 이후
Checkpointer로 전환한다.
"""

from services.agent_runtime.checkpoint.checkpointer import build

__all__ = ["build"]
