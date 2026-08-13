"""Deep Agent 런타임 공통 예외.

정본: docs/작업기록/jihun_buildingpage/2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md §12

이 모듈은 순수 예외 정의만 담는다. deepagents/DB/HTTP 어떤 것도 import하지 않는다
— definitions.py가 __post_init__에서 이 모듈을 참조하므로 순환 의존을 만들면 안 된다.
"""

from __future__ import annotations


class AgentRuntimeError(Exception):
    """Deep Agent 런타임의 예상 가능한 공통 오류."""


class InvalidExecutionTargetError(AgentRuntimeError):
    """draft와 저장된 agent_id/agent_version_id를 동시에 실행하려 했을 때(§13.2)."""


class AgentDefinitionNotFound(AgentRuntimeError):
    """agent_id가 존재하지 않을 때."""


class AgentVersionNotFound(AgentRuntimeError):
    """agent_version_id가 존재하지 않을 때."""


class ModelUnavailableError(AgentRuntimeError):
    """선택한 모델을 현재 팀/계정이 쓸 수 없을 때."""


class ToolUnavailableError(AgentRuntimeError):
    """선택한 내장 도구 또는 MCP 도구를 불러올 수 없을 때."""


class ToolContextConfigurationError(AgentRuntimeError):
    """Tool.injected_context에 선언한 이름이 CONTEXT_VALUES에 없을 때(§8.2)."""


class SubagentValidationError(AgentRuntimeError):
    """서브 에이전트 구조 검증 실패의 공통 상위 클래스(§7)."""


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
    """Loader/Factory 조립 단계에서 예상 못한 오류가 났을 때(§13.3)."""


class AgentExecutionError(AgentRuntimeError):
    """스트림이 열린 뒤 실행 자체가 실패했을 때(§13.3)."""


# HTTP 매핑(§12). API 뷰가 이 딕셔너리로 예외 → status code를 변환한다.
# AgentExecutionError는 여기 없다 — 스트림이 열린 뒤의 오류는 HTTP 상태를 바꾸지
# 않고 terminal `error` 이벤트로만 반환한다(§13.3).
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
