"""Deep Agent 실행 코어의 공통 예외."""

from __future__ import annotations


class AgentRuntimeError(Exception):
    """Deep Agent 런타임의 예상 가능한 공통 오류."""


class InvalidExecutionTargetError(AgentRuntimeError):
    """draft와 저장된 Agent version 입력이 올바르지 않을 때."""


class AgentDefinitionNotFound(AgentRuntimeError):
    """agent_id가 존재하지 않을 때."""


class AgentVersionNotFound(AgentRuntimeError):
    """agent_version_id가 존재하지 않을 때."""


class ModelUnavailableError(AgentRuntimeError):
    """선택한 모델을 현재 팀/계정이 쓸 수 없을 때."""


class ToolUnavailableError(AgentRuntimeError):
    """선택한 내장 도구 또는 MCP 도구를 불러올 수 없을 때."""


class ToolContextConfigurationError(AgentRuntimeError):
    """Tool이 지원하지 않는 서버 컨텍스트 값을 요구할 때."""


class ToolPermissionError(AgentRuntimeError):
    """현재 요청자의 역할로는 부수효과 있는 Tool을 실행할 수 없을 때.

    `filter_tools_for_role()`(노출 시점)과 별개로 `factory._to_langchain_tool()`의
    `_run()`이 실행 직전에 다시 확인하다가 걸릴 때 던진다(2026-08-14 추가) — 정상
    경로에서는 노출 필터가 이미 걸러서 여기까지 오지 않는다. 스트림 도중(도구가
    실제로 실행되는 시점)에 나므로 `AgentExecutor.run()`의 실행 중 오류 처리로
    가서 terminal `EVENT_ERROR`가 된다 — 그래서 아래 `HTTP_STATUS_BY_EXCEPTION`
    (스트림 시작 전 오류 전용)에는 넣지 않는다.
    """


class SubagentValidationError(AgentRuntimeError):
    """Child 구성 검증 실패의 공통 상위 예외."""


class SelfReferenceError(SubagentValidationError):
    """부모가 자기 자신을 서브 에이전트로 선택했을 때."""


class DuplicateSubagentError(SubagentValidationError):
    """같은 child_agent_id를 중복 선택했을 때."""


class DuplicateSubagentAliasError(SubagentValidationError):
    """같은 alias를 중복 사용했을 때."""


class InvalidSubagentAliasError(SubagentValidationError):
    """alias가 비어 있을 때."""


class InvalidDelegationDescriptionError(SubagentValidationError):
    """delegation_description이 비어 있을 때."""


class InactiveSubagentError(SubagentValidationError):
    """선택한 자식이 비활성 상태일 때."""


class SubagentCycleError(SubagentValidationError):
    """부모-자식 관계가 순환 참조를 만들 때."""


class DelegationDepthError(SubagentValidationError):
    """MVP의 1단계 위임 제한을 넘어서려 할 때(자식이 다시 자식을 가짐)."""


class SubagentPermissionError(SubagentValidationError):
    """현재 요청자가 그 자식 에이전트를 실행할 권한이 없을 때."""


class AgentBuildError(AgentRuntimeError):
    """Loader 또는 Factory에서 예상하지 못한 오류가 발생했을 때."""


class AgentExecutionError(AgentRuntimeError):
    """stream 시작 후 실행이 실패했을 때."""


# Stream 시작 전 예외를 HTTP 상태 코드로 변환한다.
# 실행 중 오류는 terminal error 이벤트로 반환하므로 여기 포함하지 않는다.
HTTP_STATUS_BY_EXCEPTION: dict[type[AgentRuntimeError], int] = {
    InvalidExecutionTargetError: 400,
    AgentDefinitionNotFound: 404,
    AgentVersionNotFound: 404,
    ModelUnavailableError: 400,
    ToolUnavailableError: 409,
    SubagentValidationError: 409,
    SubagentPermissionError: 403,
    AgentBuildError: 500,
}
