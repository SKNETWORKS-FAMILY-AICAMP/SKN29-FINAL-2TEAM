"""DB 또는 Builder draft를 Agent 실행 정의로 변환한다."""

from __future__ import annotations

from backend.db.agent_platform import AgentSubagentRepository, AgentVersionRepository
from backend.db.errors import PermissionDenied, RecordNotFound

from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.definitions import (
    AgentDefinition,
    LoadedAgentDefinition,
    SubagentDefinition,
    SubagentReference,
)
from services.agent_runtime.exceptions import AgentVersionNotFound, DelegationDepthError


class AgentDefinitionLoader:
    """저장된 특정 버전 또는 미발행 초안을 `LoadedAgentDefinition`으로 변환한다."""

    def load(
        self,
        *,
        agent_id: str,
        agent_version_id: str,
        context: RuntimeContext,
        include_subagents: bool = True,
    ) -> LoadedAgentDefinition:
        """저장된 Agent version을 런타임 정의로 변환한다.

        부모는 `include_subagents=True`, 자식은 `include_subagents=False`로 로딩한다.
        """
        row = self._fetch_definition_row(
            agent_id=agent_id, agent_version_id=agent_version_id, context=context
        )

        if not include_subagents:
            self._reject_if_has_subagents(agent_version_id=agent_version_id, context=context)
            return LoadedAgentDefinition(
                definition=self._definition_from_row(row, subagents=()),
                subagent_references=(),
            )

        refs, subagent_defs = self._load_parent_subagents(
            parent_version_id=agent_version_id, context=context
        )
        return LoadedAgentDefinition(
            definition=self._definition_from_row(row, subagents=subagent_defs),
            subagent_references=refs,
        )

    def from_draft(self, *, draft: dict, context: RuntimeContext) -> LoadedAgentDefinition:
        """Builder draft와 저장된 Child version을 테스트용 정의로 변환한다.

        `agent_id`는 기본 `None`(저장 전 순수 초안)이지만, `draft["agent_id"]`가
        있으면 그 값을 쓴다(2026-08-14 추가) — `services.agent_runtime
        .legacy_bridge`가 **이미 저장된** 레거시 `agent` 행을 draft 모양으로
        옮길 때 실제 agent_id를 실어 보낸다. 이게 없으면
        `agent_run.agent_id`(NOT NULL)를 못 채워 실행 로그 적재가 깨진다.
        `agent_version_id`는 항상 `None`이다 — draft에는 애초에 그 개념이 없다
        (저장된 버전이 아니므로).
        """
        refs: list[SubagentReference] = []
        subagent_defs: list[SubagentDefinition] = []

        for item in draft.get("subagents") or ():
            ref, subagent_def = self._resolve_draft_subagent(item=item, context=context)
            refs.append(ref)
            subagent_defs.append(subagent_def)

        definition = AgentDefinition(
            agent_id=draft.get("agent_id"),
            agent_version_id=None,
            name=draft["name"],
            description=draft["description"],
            system_prompt=draft["system_prompt"],
            model=draft["model"],
            reasoning_effort=draft["reasoning_effort"],
            max_iterations=draft["max_iterations"],
            tool_refs=tuple(draft.get("tool_refs") or ()),
            subagents=tuple(subagent_defs),
        )
        return LoadedAgentDefinition(definition=definition, subagent_references=tuple(refs))

    # 저장된 Agent version 로딩

    @staticmethod
    def _fetch_definition_row(*, agent_id: str, agent_version_id: str, context: RuntimeContext) -> dict:
        try:
            return AgentVersionRepository.get_definition(
                agent_id=agent_id,
                agent_version_id=agent_version_id,
                account_id=context.account_id,
                team_id=context.team_id,
            )
        except (RecordNotFound, PermissionDenied) as exc:
            raise AgentVersionNotFound(
                f"에이전트 버전을 찾을 수 없습니다: {agent_id}/{agent_version_id}"
            ) from exc

    @staticmethod
    def _definition_from_row(row: dict, *, subagents: tuple[SubagentDefinition, ...]) -> AgentDefinition:
        return AgentDefinition(
            agent_id=row["agent_id"],
            agent_version_id=row["agent_version_id"],
            name=row["name"],
            description=row["description"],
            system_prompt=row["system_prompt"],
            model=row["model"],
            reasoning_effort=row["reasoning_effort"],
            max_iterations=row["max_iterations"],
            tool_refs=tuple(row["tool_refs"]),
            subagents=subagents,
        )

    @staticmethod
    def _reject_if_has_subagents(*, agent_version_id: str, context: RuntimeContext) -> None:
        """Child가 다른 Child를 갖는 2단계 위임을 차단한다."""
        child_refs = AgentSubagentRepository.list_for_parent_version(
            parent_version_id=agent_version_id,
            account_id=context.account_id,
            team_id=context.team_id,
        )
        if child_refs:
            raise DelegationDepthError(
                f"'{agent_version_id}'는 이미 서브 에이전트를 갖고 있어 "
                "MVP의 1단계 위임 제한을 넘어섭니다."
            )

    # Root에 연결된 Child 로딩

    def _load_parent_subagents(
        self, *, parent_version_id: str, context: RuntimeContext
    ) -> tuple[tuple[SubagentReference, ...], tuple[SubagentDefinition, ...]]:
        """Root version의 Child reference와 실행 정의를 조립한다."""
        rows = AgentSubagentRepository.list_for_parent_version(
            parent_version_id=parent_version_id,
            account_id=context.account_id,
            team_id=context.team_id,
        )

        refs: list[SubagentReference] = []
        subagent_defs: list[SubagentDefinition] = []
        for row in rows:
            ref = SubagentReference(
                child_agent_id=row["child_agent_id"],
                child_version_id=row["child_version_id"],
                alias=row["alias"],
                delegation_description=row["delegation_description"],
                is_active=row["is_active"],
                can_execute=row["can_execute"],
                has_subagents=row["has_subagents"],
            )
            refs.append(ref)
            subagent_defs.append(self._fetch_subagent_definition(ref, context=context))

        return tuple(refs), tuple(subagent_defs)

    def _fetch_subagent_definition(self, ref: SubagentReference, *, context: RuntimeContext) -> SubagentDefinition:
        """Child reference를 실행에 필요한 `SubagentDefinition`으로 변환한다."""
        if not ref.can_execute:
            return self._placeholder_subagent_definition(ref)

        try:
            row = AgentVersionRepository.get_definition(
                agent_id=ref.child_agent_id,
                agent_version_id=ref.child_version_id,
                account_id=context.account_id,
                team_id=context.team_id,
            )
        except (RecordNotFound, PermissionDenied):
            # 조회 사이에 권한이나 데이터가 바뀐 경우도 검증 단계로 넘긴다.
            return self._placeholder_subagent_definition(ref)

        return self._subagent_definition_from_row(row, ref)

    @staticmethod
    def _subagent_definition_from_row(row: dict, ref: SubagentReference) -> SubagentDefinition:
        return SubagentDefinition(
            agent_id=row["agent_id"],
            agent_version_id=row["agent_version_id"],
            name=row["name"],
            description=row["description"],
            system_prompt=row["system_prompt"],
            model=row["model"],
            reasoning_effort=row["reasoning_effort"],
            max_iterations=row["max_iterations"],
            alias=ref.alias,
            delegation_description=ref.delegation_description,
            tool_refs=tuple(row["tool_refs"]),
        )

    @staticmethod
    def _placeholder_subagent_definition(ref: SubagentReference) -> SubagentDefinition:
        """권한 검증에서 거부될 Child의 자리를 유지하는 임시 정의를 만든다."""
        return SubagentDefinition(
            agent_id=ref.child_agent_id,
            agent_version_id=ref.child_version_id,
            name=ref.alias,
            description=ref.delegation_description,
            system_prompt="",
            model="",
            reasoning_effort="",
            max_iterations=0,
            alias=ref.alias,
            delegation_description=ref.delegation_description,
            tool_refs=(),
        )

    # Builder draft에서 선택한 Child 로딩

    def _resolve_draft_subagent(
        self, *, item: dict, context: RuntimeContext
    ) -> tuple[SubagentReference, SubagentDefinition]:
        child_agent_id = item["child_agent_id"]
        child_version_id = item["child_version_id"]
        alias = item["alias"]
        delegation_description = item["delegation_description"]

        try:
            row = AgentVersionRepository.get_definition(
                agent_id=child_agent_id,
                agent_version_id=child_version_id,
                account_id=context.account_id,
                team_id=context.team_id,
            )
        except (RecordNotFound, PermissionDenied):
            ref = SubagentReference(
                child_agent_id=child_agent_id,
                child_version_id=child_version_id,
                alias=alias,
                delegation_description=delegation_description,
                is_active=False,
                can_execute=False,
                has_subagents=False,
            )
            return ref, self._placeholder_subagent_definition(ref)

        # 조회가 성공했으므로 현재 팀에서 실행할 수 있다.
        grandchildren = AgentSubagentRepository.list_for_parent_version(
            parent_version_id=child_version_id,
            account_id=context.account_id,
            team_id=context.team_id,
        )
        ref = SubagentReference(
            child_agent_id=child_agent_id,
            child_version_id=child_version_id,
            alias=alias,
            delegation_description=delegation_description,
            # 본인 소유 DRAFT도 된다 — `AgentSubagentRepository.
            # list_for_parent_version()`/`_build_subagent_refs()`와 같은 완화
            # (2026-08-19, 저장된 부모 실행 경로에서 먼저 발견·수정). Builder Test
            # Run(이 함수)에서만 다르게 막을 이유가 없다.
            is_active=row["agent_status"] == "ACTIVE"
            or (row["agent_status"] == "DRAFT" and row["agent_owner_account_id"] == context.account_id),
            can_execute=True,
            has_subagents=bool(grandchildren),
        )
        return ref, self._subagent_definition_from_row(row, ref)


__all__ = ["AgentDefinitionLoader"]
