"""DB 또는 빌더 초안에서 에이전트 설정을 읽어 정의 객체로 변환한다.

정본: docs/작업기록/jihun_buildingpage/2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md §6

⚠ 미구현. 이 프로젝트는 Django ORM을 쓰지 않는다 — 데이터 접근은
`backend/db/`의 psycopg 직접 SQL Repository 몫이다(docs/TO-BE/작업목록.md 공통
주의사항). 이 파일이 실제로 동작하려면 먼저 `backend/db/agent_platform.py`에
`AgentVersionRepository.get_definition()`과
`AgentSubagentRepository.list_for_parent_version()`(§6.1)이 추가돼야 한다 —
지금은 그 두 Repository가 존재하지 않는다.

Repository가 반환해야 할 형태(§6.1 예시)는 doc02를 참고할 것. 특히
"비활성/권한 없는 자식을 조용히 목록에서 제외하지 않는다 — is_active·can_execute를
명시해야 정확한 실패 사유를 만들 수 있다"는 원칙을 지킬 것.
"""

from __future__ import annotations

from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.definitions import LoadedAgentDefinition


class AgentDefinitionLoader:
    """저장된 특정 버전 또는 미발행 초안을 LoadedAgentDefinition으로 변환한다."""

    def load(
        self,
        *,
        agent_id: str,
        agent_version_id: str,
        context: RuntimeContext,
        include_subagents: bool = True,
    ) -> LoadedAgentDefinition:
        """저장된 특정 버전을 런타임 정의로 변환한다(§6.2).

        부모는 include_subagents=True, 자식은 include_subagents=False로 로딩한다.
        자식 정의에 다시 서브 에이전트가 존재하면 조용히 제거하지 않고
        DelegationDepthError를 낸다(§6.2).
        """
        raise NotImplementedError(
            "backend/db/agent_platform.py에 AgentVersionRepository·"
            "AgentSubagentRepository 추가 후 구현."
        )

    def from_draft(
        self,
        *,
        draft: dict,
        context: RuntimeContext,
    ) -> LoadedAgentDefinition:
        """아직 발행하지 않은 부모 초안을 테스트 정의로 변환한다(§6.2).

        초안 테스트는 agent_id/agent_version_id를 None으로 둘 수 있다
        (definitions.AgentDefinition 참조). 저장되지 않은 초안을 서브 에이전트로
        쓰는 경로는 여기서 원천적으로 안 만든다 — draft에 subagents가 있어도
        전부 저장된 agent_id/agent_version_id를 가진 것만 통과시킨다.
        """
        raise NotImplementedError(
            "빌더 화면의 draft dict 스키마(02 §16 빌더 API 요청 계약) 확정 후 구현."
        )
