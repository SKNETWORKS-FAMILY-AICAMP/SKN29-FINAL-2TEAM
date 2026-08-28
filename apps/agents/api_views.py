"""에이전트 정의 API — Builder 가 쓴다.

2026-08-22에 레거시 비버전 스키마(`agent`/`agent_tool`)의 CRUD·활성화·빌더
테스트 실행을 전부 지웠다. 남은 것은 두 갈래다 — 어느 스키마든 공유하던
카탈로그 조회(도구·커스텀 모델)와, 새 버전 스키마(`agents`/`agent_versions`)의
정의 API.
"""

import logging

import psycopg
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import BearerTokenAuthentication
from apps.accounts.permissions import require_owner_or_leader
from backend.db.agent_platform import (
    AgentCrudRepository,
    AgentVersionCrudRepository,
    CustomModelRepository,
)
from backend.db.errors import (
    PermissionDenied,
    RecordNotFound,
    ReferenceNotFound,
    RepositoryError,
)
from services.agent_builder import check_definition
from services.agent_runtime.exceptions import AgentRuntimeError, HTTP_STATUS_BY_EXCEPTION

from .serializers import (
    AGENT_MODELS,
    AgentVersionFavoriteSerializer,
    AgentVersionPublishSerializer,
    agent_version_response,
    builtin_tool_response,
    mcp_tool_response,
)

logger = logging.getLogger(__name__)


def _repository_error_response(exc: Exception) -> Response:
    if isinstance(exc, RecordNotFound):
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, PermissionDenied):
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    if isinstance(exc, ReferenceNotFound):
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    if isinstance(exc, RepositoryError):
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(
        {"detail": "데이터베이스 요청을 처리할 수 없습니다.", "error": exc.__class__.__name__},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _agent_runtime_error_response(exc: AgentRuntimeError) -> Response:
    """`services.agent_runtime.exceptions`를 HTTP 응답으로 바꾼다(02 §12).

    `type(exc).__mro__`를 위에서부터 훑어 `HTTP_STATUS_BY_EXCEPTION`에 먼저
    걸리는 클래스를 쓴다 — 예를 들어 `SubagentPermissionError`는
    `SubagentValidationError`의 하위 클래스라, 매핑을 그냥 `isinstance`로 훑으면
    등록 순서에 따라 403 대신 409로 잘못 걸릴 수 있다. MRO 순회는 항상 가장
    구체적인 클래스부터 맞으므로 이 문제가 없다.
    """

    for cls in type(exc).__mro__:
        if cls in HTTP_STATUS_BY_EXCEPTION:
            return Response({"detail": str(exc)}, status=HTTP_STATUS_BY_EXCEPTION[cls])
    return Response(
        {"detail": "요청을 처리할 수 없습니다.", "error": exc.__class__.__name__},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


class AuthenticatedAPIView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]


def _model_rejection(account_id: str, model: str | None) -> Response | None:
    """이 팀이 고를 수 있는 모델인가. 괜찮으면 `None`, 아니면 그대로 돌려줄 응답.

    고를 수 있는 목록은 팀마다 다르다 — 기본 제공 6종 + 그 팀이 등록한 커스텀
    모델. `serializer.ChoiceField`로는 못 막아서(팀을 모른다) 여기서 대조한다.
    기본 제공이면 DB를 안 본다 — 커스텀 목록을 못 읽는다고 기본 모델조차
    못 고르면 안 된다.
    """

    if not model or model in AGENT_MODELS:
        return None
    try:
        customs = {row["model"] for row in CustomModelRepository.list_for_account(account_id)}
    except (RepositoryError, psycopg.Error) as exc:
        return _repository_error_response(exc)
    if model in customs:
        return None
    return Response(
        {"detail": f"{model} 은 고를 수 없는 모델입니다."}, status=status.HTTP_400_BAD_REQUEST
    )


class AgentToolCatalogAPIView(AuthenticatedAPIView):
    """편집 화면의 도구 체크 목록 — 내장 + 팀의 MCP 도구.

    화면이 내장 목록을 따로 적어 두지 않게 서버가 준다. 적어 두면 Registry 가
    바뀔 때 화면만 옛 목록으로 남는다(실제로 tool id 계약이 두 번 바뀌었다).
    """

    def get(self, request):
        try:
            mcp = AgentCrudRepository.team_tool_refs(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(builtin_tool_response() + mcp_tool_response(mcp))


class CustomModelAPIView(AuthenticatedAPIView):
    """이 팀에 등록된 모델 API. 읽기 전용 — 등록·삭제는 운영자 콘솔
    (`/api/ops/models/`)이 한다. 키는 돌려주지 않는다 — 이름·주소·모델만 준다.
    """

    def get(self, request):
        try:
            return Response(CustomModelRepository.list_for_account(request.user.account_id))
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)


def _tool_catalog(account_id: str) -> dict[str, dict]:
    """**검증용** 도구 전체(내장 + 팀 MCP) — `tool_ref`로 찾아본다.

    `builtin_tool_response()`(고르는 화면이 쓰는 목록)와는 다르다 —
    `ALWAYS_ON_TOOL_REFS`(예: `skill_register`)와 `AGENT_ONLY_TOOL_REFS`(예:
    `task_extraction`, 「업무 추출 에이전트」 전용)는 화면에서 고를 수 없지만
    "알려진 도구"이긴 하다. 여기서 안 넣으면 `check_definition`이 "카탈로그에
    없는 도구"로 본다 — 그 도구를 `tool_refs`에 저장한 에이전트가 있으면
    `activate`/편집(DB에 저장된 `tool_refs`를 다시 검증하는 경로)에서
    막힌다. 검증 카탈로그는 넉넉하게, 고르는 화면은 좁게 — 둘의 목적이 다르다.
    """

    from services.harness.registry import (
        AGENT_ONLY_TOOL_REFS,
        ALWAYS_ON_TOOL_REFS,
        BUILTIN_TOOLS,
    )

    mcp = AgentCrudRepository.team_tool_refs(account_id)
    catalog = {row["tool_ref"]: row for row in builtin_tool_response() + mcp_tool_response(mcp)}
    for ref in ALWAYS_ON_TOOL_REFS | AGENT_ONLY_TOOL_REFS:
        tool = BUILTIN_TOOLS.get(ref)
        if tool is not None and ref not in catalog:
            catalog[ref] = {
                "tool_ref": tool.ref,
                "name": tool.name,
                "description": tool.description,
                "source": "기본 제공",
                "category": tool.category,
                "provider": tool.provider,
                "capability": tool.capability,
                "requires_connection": tool.requires_connection,
                "side_effect": tool.side_effect,
                "input_schema": tool.input_schema,
            }
    return catalog


def _check_tool_refs(*, account_id: str, tool_refs: list[str]) -> str | None:
    """`AgentListCreateAPIView`/`AgentDetailAPIView`/`AgentActivateAPIView`가 함께 쓰는
    구조 검증 — 도구 참조가 실제로 존재하는지, 중복 선택은 없는지만 본다."""

    return check_definition(tool_refs=tool_refs, catalog=_tool_catalog(account_id))


def _cascade_activate_draft_subagents(*, agent_id: str, account_id: str) -> list[str]:
    """부모가 활성화되거나 이미 활성 상태에서 재발행될 때, 그 버전이 참조하는
    개인 DRAFT 서브 에이전트를 같이 활성화한다(2026-08-18).

    활성화와 같은 재검증(모델·도구)을 통과 못 하면 그 자식만 조용히
    건너뛴다 — 부모 활성화 자체는 막지 않는다. 통과한 것만 활성화하고 이름을
    모아 돌려준다(호출부가 토스트로 알린다).
    """

    try:
        children = AgentVersionCrudRepository.list_dependent_draft_children(agent_id=agent_id)
    except (RepositoryError, psycopg.Error):
        return []

    activated: list[str] = []
    for child in children:
        if _model_rejection(account_id, child.get("model")) is not None:
            continue
        try:
            if _check_tool_refs(account_id=account_id, tool_refs=list(child.get("tool_refs") or [])) is not None:
                continue
        except (RepositoryError, psycopg.Error):
            continue
        try:
            AgentVersionCrudRepository.activate_cascaded_child(agent_id=child["agent_id"])
        except (RepositoryError, psycopg.Error):
            continue
        activated.append(child["name"])
    return activated


# =========================================================================
# 에이전트 정의 CRUD — agents/agent_versions/agent_version_tools/
# agent_version_subagents 네 테이블. 계약: docs/작업기록/Deep_Agents/
# 2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md
# =========================================================================


class AgentVersionListCreateAPIView(AuthenticatedAPIView):
    def get(self, request):
        try:
            rows = AgentVersionCrudRepository.list_for_team(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response([agent_version_response(row) for row in rows])

    def post(self, request):
        """새 논리적 에이전트 + 첫 버전을 함께 발행한다."""

        serializer = AgentVersionPublishSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        fields = {
            key: data[key]
            for key in (
                "name", "description", "system_prompt", "model",
                "reasoning_effort", "max_iterations",
            )
        }
        account_id = request.user.account_id

        rejection = _model_rejection(account_id, fields.get("model"))
        if rejection is not None:
            return rejection
        try:
            blocker = _check_tool_refs(account_id=account_id, tool_refs=data["tool_refs"])
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        if blocker is not None:
            return Response({"detail": blocker}, status=status.HTTP_400_BAD_REQUEST)

        try:
            row = AgentVersionCrudRepository.publish(
                agent_id=None,
                account_id=account_id,
                fields=fields,
                tool_refs=data["tool_refs"],
                subagents=data["subagents"],
            )
        except AgentRuntimeError as exc:
            return _agent_runtime_error_response(exc)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(agent_version_response(row), status=status.HTTP_201_CREATED)


class AgentVersionDetailAPIView(AuthenticatedAPIView):
    def get(self, request, agent_id):
        try:
            row = AgentVersionCrudRepository.get(
                agent_id=agent_id, account_id=request.user.account_id
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(agent_version_response(row))

    def put(self, request, agent_id):
        """기존 논리적 에이전트에 새 버전을 발행한다.

        일반적인 PUT과 달리 멱등하지 않다 — `agent_versions`가 불변이라
        "덮어쓰기"가 없다. 호출할 때마다 새 버전이 생기고 `current_version_id`만
        옮겨간다. 옛 버전을 고정 참조하는 세션·부모 에이전트는 그대로 쓴다.
        """

        serializer = AgentVersionPublishSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        fields = {
            key: data[key]
            for key in (
                "name", "description", "system_prompt", "model",
                "reasoning_effort", "max_iterations",
            )
        }
        account_id = request.user.account_id

        # 만든 사람이거나 팀장만 새 버전을 발행할 수 있다.
        try:
            current = AgentVersionCrudRepository.get(agent_id=agent_id, account_id=account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        denied = require_owner_or_leader(
            account_id,
            current.get("owner_account_id"),
            "만든 사람이거나 팀장만 이 에이전트의 새 버전을 발행할 수 있습니다.",
        )
        if denied is not None:
            return denied

        rejection = _model_rejection(account_id, fields.get("model"))
        if rejection is not None:
            return rejection
        try:
            blocker = _check_tool_refs(account_id=account_id, tool_refs=data["tool_refs"])
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        if blocker is not None:
            return Response({"detail": blocker}, status=status.HTTP_400_BAD_REQUEST)

        try:
            row = AgentVersionCrudRepository.publish(
                agent_id=agent_id,
                account_id=account_id,
                fields=fields,
                tool_refs=data["tool_refs"],
                subagents=data["subagents"],
            )
        except AgentRuntimeError as exc:
            return _agent_runtime_error_response(exc)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        # 이미 ACTIVE였던 에이전트가 새 버전에서 개인 DRAFT 서브 에이전트를
        # 새로 참조하면 여기서 같이 활성화한다 — 지금 막 활성화하는 경우는
        # 활성화 API 쪽이 이미 처리하므로 제외한다.
        cascaded_names: list[str] = []
        if current.get("status") == "ACTIVE":
            cascaded_names = _cascade_activate_draft_subagents(agent_id=agent_id, account_id=account_id)
        response_body = agent_version_response(row)
        if cascaded_names:
            response_body["cascaded_subagent_names"] = cascaded_names
        return Response(response_body)

    def delete(self, request, agent_id):
        """만든 사람이거나 팀장만 지울 수 있다. 실제로는 ARCHIVED로 내린다 —
        `AgentVersionCrudRepository.delete` 참고."""

        account_id = request.user.account_id
        try:
            agent = AgentVersionCrudRepository.get(agent_id=agent_id, account_id=account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        denied = require_owner_or_leader(
            account_id,
            agent.get("owner_account_id"),
            "만든 사람이거나 팀장만 이 에이전트를 지울 수 있습니다.",
        )
        if denied is not None:
            return denied

        try:
            AgentVersionCrudRepository.delete(agent_id=agent_id, account_id=account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AgentVersionDependentsAPIView(AuthenticatedAPIView):
    """이 에이전트를 서브 에이전트로 쓰는 다른 에이전트 이름 목록. 삭제 전
    안내용 — 실제 차단은 `AgentVersionDetailAPIView.delete`가 한 번 더 한다.
    """

    def get(self, request, agent_id):
        try:
            parents = AgentVersionCrudRepository.list_dependents(
                agent_id=agent_id, account_id=request.user.account_id
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response({"parent_names": parents})


class AgentVersionActivateAPIView(AuthenticatedAPIView):
    """DRAFT/DISABLED → ACTIVE. 옛 `AgentActivateAPIView`와 같은 이유로 재검증한다
    — 버전 자체(system_prompt 등)는 불변이어도, 그 버전이 참조하는 팀의 커스텀
    모델·MCP 도구는 불변이 아니다. 발행 시점엔 있던 것이 활성화 시점엔 사라졌을
    수 있다."""

    def post(self, request, agent_id):
        account_id = request.user.account_id
        try:
            agent = AgentVersionCrudRepository.get(agent_id=agent_id, account_id=account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        # put()과 같은 규칙 — 만든 사람이거나 팀장만 활성화할 수 있다.
        denied = require_owner_or_leader(
            account_id,
            agent.get("owner_account_id"),
            "만든 사람이거나 팀장만 이 에이전트를 활성화할 수 있습니다.",
        )
        if denied is not None:
            return denied

        rejection = _model_rejection(account_id, agent.get("model"))
        if rejection is not None:
            return rejection
        try:
            blocker = _check_tool_refs(account_id=account_id, tool_refs=agent["tool_refs"])
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        if blocker is not None:
            return Response({"detail": blocker}, status=status.HTTP_409_CONFLICT)

        try:
            row = AgentVersionCrudRepository.set_status(
                agent_id=agent_id, account_id=account_id, status="ACTIVE"
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        # 이 버전이 참조하는 개인 DRAFT 서브 에이전트를 같이 활성화한다.
        cascaded_names = _cascade_activate_draft_subagents(agent_id=agent_id, account_id=account_id)
        response_body = agent_version_response(row)
        if cascaded_names:
            response_body["cascaded_subagent_names"] = cascaded_names
        return Response(response_body)


class AgentVersionDisableAPIView(AuthenticatedAPIView):
    """ACTIVE → DISABLED. 검증 없이 바로 내린다 — 끄는 쪽은 항상 안전하다."""

    def post(self, request, agent_id):
        account_id = request.user.account_id
        try:
            agent = AgentVersionCrudRepository.get(agent_id=agent_id, account_id=account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        # put()과 같은 규칙 — 만든 사람이거나 팀장만 사용 중지할 수 있다.
        denied = require_owner_or_leader(
            account_id,
            agent.get("owner_account_id"),
            "만든 사람이거나 팀장만 이 에이전트를 사용 중지할 수 있습니다.",
        )
        if denied is not None:
            return denied

        try:
            row = AgentVersionCrudRepository.set_status(
                agent_id=agent_id, account_id=account_id, status="DISABLED"
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(agent_version_response(row))


class AgentVersionFavoriteAPIView(AuthenticatedAPIView):
    """즐겨찾기 별 토글(2026-08-18). 소유자·팀장 제한이 없다 — 자기 시야에
    있는 에이전트(팀 공유 + 본인 DRAFT)라면 누구든 즐겨찾기할 수 있다.
    """

    def put(self, request, agent_id):
        serializer = AgentVersionFavoriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        account_id = request.user.account_id
        try:
            row = AgentVersionCrudRepository.set_favorite(
                agent_id=agent_id,
                account_id=account_id,
                favorite=serializer.validated_data["favorite"],
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(agent_version_response(row))
