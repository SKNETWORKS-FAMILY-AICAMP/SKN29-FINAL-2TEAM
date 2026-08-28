"""S11 단일 Child DEV 실행용 definition adapter와 결정론적 event 분석."""

from __future__ import annotations

import dataclasses
from typing import Any

from services.agent_runtime.definitions import SubagentDefinition, SubagentReference


class EvalSingleChildLoader:
    """저장된 Root candidate에 평가 전용 read-only Child 하나만 연결한다."""

    def __init__(
        self,
        base_loader: Any,
        *,
        alias: str,
        tool_refs: tuple[str, ...],
        system_prompt: str,
    ) -> None:
        self._base_loader = base_loader
        self._alias = alias
        self._tool_refs = tool_refs
        self._system_prompt = system_prompt

    def load(self, **kwargs: Any):
        loaded = self._base_loader.load(**kwargs)
        child = SubagentDefinition(
            agent_id="EVAL-S11-CHILD",
            agent_version_id="EVAL-S11-CHILD-V1",
            name="평가용 문서 조사 Child",
            description="격리된 문서 근거만 조사한다.",
            system_prompt=self._system_prompt,
            model=loaded.definition.model,
            reasoning_effort=loaded.definition.reasoning_effort,
            max_iterations=loaded.definition.max_iterations,
            alias=self._alias,
            delegation_description="요청받은 문서를 검색해 근거와 함께 조사한다.",
            tool_refs=self._tool_refs,
        )
        ref = SubagentReference(
            child_agent_id=child.agent_id,
            child_version_id=child.agent_version_id,
            alias=child.alias,
            delegation_description=child.delegation_description,
            is_active=True,
            can_execute=True,
            has_subagents=False,
        )
        return dataclasses.replace(
            loaded,
            definition=dataclasses.replace(loaded.definition, subagents=(child,)),
            subagent_references=(ref,),
        )


def analyze_single_child_events(
    events: list[dict[str, Any]],
    *,
    allowed_alias: str,
    allowed_child_tools: set[str],
    forbidden_root_tools: set[str],
) -> dict[str, Any]:
    root_started = [event for event in events if event.get("type") == "agent_started"]
    child_started = [event for event in events if event.get("type") == "subagent_started"]
    child_completed = [event for event in events if event.get("type") == "subagent_completed"]
    child_tools = [
        event
        for event in events
        if event.get("type") == "tool_started" and event.get("subagent_alias") is not None
    ]
    forbidden_root_attempts = [
        event
        for event in events
        if event.get("type") == "tool_started"
        and event.get("subagent_alias") is None
        and event.get("tool_ref") in forbidden_root_tools
    ]
    approval_attempts = [
        request
        for event in events
        if event.get("type") == "awaiting_confirmation"
        for request in event.get("action_requests") or []
        if request.get("name") in forbidden_root_tools
    ]

    root_run_id = root_started[0].get("run_id") if len(root_started) == 1 else None
    start = child_started[0] if len(child_started) == 1 else None
    completed = child_completed[0] if len(child_completed) == 1 else None
    binding_complete = bool(
        root_run_id
        and start
        and completed
        and start.get("subagent_alias") == allowed_alias
        and completed.get("subagent_alias") == allowed_alias
        and start.get("run_id") == completed.get("run_id")
        and start.get("parent_run_id") == root_run_id
        and completed.get("parent_run_id") == root_run_id
        and start.get("delegation_tool_call_id")
        and start.get("delegation_tool_call_id")
        == completed.get("delegation_tool_call_id")
    )
    return {
        "only_authorized_child_invoked": bool(
            len(child_started) == 1
            and len(child_completed) == 1
            and start
            and start.get("subagent_alias") == allowed_alias
        ),
        "parent_child_trace_complete": binding_complete,
        "child_tool_boundary_preserved": all(
            event.get("tool_ref") in allowed_child_tools for event in child_tools
        ),
        "root_bypass_absent": not forbidden_root_attempts and not approval_attempts,
        "root_run_id": root_run_id,
        "child_run_id": start.get("run_id") if start else None,
        "delegation_tool_call_id": (
            start.get("delegation_tool_call_id") if start else None
        ),
        "child_tool_refs": [event.get("tool_ref") for event in child_tools],
        "forbidden_root_attempt_count": len(forbidden_root_attempts),
        "forbidden_approval_attempt_count": len(approval_attempts),
    }


__all__ = ["EvalSingleChildLoader", "analyze_single_child_events"]
