"""`executor._agent_execution_failure_event()` 단위 테스트.

2026-08-25 — 모델·도구 호출 상한 초과(`ModelCallLimitExceededError`/
`ToolCallLimitExceededError`, `exit_behavior="error"`)를 만나면 지금까지는
"에이전트 실행 중 오류가 발생했습니다."라는 일반 문구만 사용자에게 갔다.
호출 상한 초과도 사람이 고칠 수 있는 사유(요청을 나눠서 다시 시도)이므로
전용 한국어 문구로 바꾸는 것을 확인한다.
"""

from django.test import SimpleTestCase
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError

from backend.db.errors import RepositoryError
from services.agent_runtime.events import EVENT_ERROR
from services.agent_runtime.executor import _agent_execution_failure_event


class AgentExecutionFailureEventTests(SimpleTestCase):
    def test_model_call_limit_exceeded_gets_korean_actionable_message(self):
        exc = ModelCallLimitExceededError(thread_count=0, run_count=6, thread_limit=None, run_limit=6)

        event = _agent_execution_failure_event(
            exc, agent_id="AG001", agent_version_id="AV001", run_id="RUN001"
        )

        self.assertEqual(event["type"], EVENT_ERROR)
        self.assertIn("호출 횟수가 한도를 넘어", event["message"])
        self.assertNotIn("run limit", event["message"])  # 원문 영어 문구가 새지 않는다

    def test_tool_call_limit_exceeded_gets_korean_actionable_message(self):
        exc = ToolCallLimitExceededError(thread_count=0, run_count=100, thread_limit=None, run_limit=100)

        event = _agent_execution_failure_event(
            exc, agent_id="AG001", agent_version_id="AV001", run_id="RUN001"
        )

        self.assertIn("호출 횟수가 한도를 넘어", event["message"])

    def test_speakable_error_still_passes_through_original_message(self):
        """기존 동작 회귀 방지 — `RepositoryError`(SPEAKABLE_ERRORS)는 원문 그대로."""
        exc = RepositoryError("프로젝트를 찾을 수 없습니다")

        event = _agent_execution_failure_event(
            exc, agent_id="AG001", agent_version_id="AV001", run_id="RUN001"
        )

        self.assertEqual(event["message"], "프로젝트를 찾을 수 없습니다")

    def test_unspeakable_error_still_gets_generic_message(self):
        """기존 동작 회귀 방지 — 화이트리스트 밖 예외는 여전히 뭉뚱그린 문구."""
        event = _agent_execution_failure_event(
            RuntimeError("internal stack trace detail"),
            agent_id="AG001",
            agent_version_id="AV001",
            run_id="RUN001",
        )

        self.assertEqual(event["message"], "에이전트 실행 중 오류가 발생했습니다.")
