"""Agent CRUD API — Builder 가 쓴다 (개발지시_3차 단계 2)."""

import json
import logging

import psycopg
from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import BearerTokenAuthentication
from backend.db import AccountRepository
from backend.db.agent_platform import AgentCrudRepository
from backend.db.errors import (
    PermissionDenied,
    RecordNotFound,
    ReferenceNotFound,
    RepositoryError,
)
from services.agent_builder import review_builder_input, review_instruction
from services.document_pipeline.errors import PipelineConfigurationError
from services.harness import check_tools, run_agent

from .serializers import (
    AgentWriteSerializer,
    BuilderCheckSerializer,
    BuilderInstructionRecheckSerializer,
    BuilderTestRunSerializer,
    BuilderToolCheckSerializer,
    agent_response,
    builder_check_response,
    builder_instruction_recheck_response,
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


class AuthenticatedAPIView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]


def _split(data: dict) -> tuple[dict, list[str]]:
    fields = dict(data)
    return fields, fields.pop("tool_refs")


class AgentListCreateAPIView(AuthenticatedAPIView):
    def get(self, request):
        try:
            rows = AgentCrudRepository.list_for_team(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response([agent_response(row) for row in rows])

    def post(self, request):
        serializer = AgentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields, tool_refs = _split(serializer.validated_data)
        try:
            row = AgentCrudRepository.create(
                account_id=request.user.account_id, fields=fields, tool_refs=tool_refs
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(agent_response(row), status=status.HTTP_201_CREATED)


class AgentDetailAPIView(AuthenticatedAPIView):
    def get(self, request, agent_id):
        try:
            row = AgentCrudRepository.get(agent_id=agent_id, account_id=request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(agent_response(row))

    def put(self, request, agent_id):
        serializer = AgentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields, tool_refs = _split(serializer.validated_data)
        try:
            row = AgentCrudRepository.update(
                agent_id=agent_id,
                account_id=request.user.account_id,
                fields=fields,
                tool_refs=tool_refs,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(agent_response(row))

    def delete(self, request, agent_id):
        try:
            AgentCrudRepository.delete(agent_id=agent_id, account_id=request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


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


def _tool_catalog(account_id: str) -> dict[str, dict]:
    """빌더가 선택할 수 있는 도구 전체(내장 + 팀 MCP) — `tool_ref`로 찾아본다."""

    mcp = AgentCrudRepository.team_tool_refs(account_id)
    return {row["tool_ref"]: row for row in builtin_tool_response() + mcp_tool_response(mcp)}


def _run_builder_check(*, account_id: str, name: str, description: str, behavior: str, tool_refs: list[str]):
    """`AgentBuilderCheckAPIView`와 `AgentActivateAPIView`가 함께 쓰는 1단계 검토 호출.

    코드 검증(로컬/DB) → LLM 의미 검증을 `review_builder_input`이 순서대로 묶는다.
    실패하면 `PipelineConfigurationError`/`ValueError`를 그대로 올린다 — 호출자마다
    "검증 서비스 자체가 죽었을 때 무엇을 할지"가 다르다(검증 화면은 알려야 하고,
    활성화는 그것 때문에 막지 않는다).
    """

    return review_builder_input(
        name=name,
        description=description,
        behavior=behavior,
        tool_refs=tool_refs,
        catalog=_tool_catalog(account_id),
    )


class AgentBuilderCheckAPIView(AuthenticatedAPIView):
    """이름·설명·행동 지시·도구 선택이 서로 맞는지 LLM으로 검토한다.

    저장 여부와 무관하다 — 「검증」 1단계가 언제든 다시 부른다.
    """

    def post(self, request):
        serializer = BuilderCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        account_id = request.user.account_id

        try:
            result = _run_builder_check(
                account_id=account_id,
                name=data["name"],
                description=data["description"],
                behavior=data["behavior"],
                tool_refs=data["tool_refs"],
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        except PipelineConfigurationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(builder_check_response(result))


def _builder_test_events(*, draft: dict, user_input: str, account_id: str):
    """빌더 테스트 실행 이벤트를 NDJSON 한 줄씩 내보낸다.

    응답이 이미 시작된 뒤라 예외를 상태 코드로 알릴 수 없다 — 마지막 줄에
    `error` 이벤트로 실어 보낸다.
    """

    try:
        for event in run_agent(None, user_input, {"account_id": account_id}, draft=draft, dry_run=True):
            yield json.dumps(event, ensure_ascii=False, default=str) + "\n"
    except Exception as exc:  # noqa: BLE001 - 스트림 중에는 500을 낼 수 없다
        logger.exception("빌더 테스트 실행 중 오류")
        yield (
            json.dumps(
                {"type": "error", "detail": f"테스트 실행에 실패했습니다: {exc.__class__.__name__}"},
                ensure_ascii=False,
            )
            + "\n"
        )


class AgentBuilderTestRunAPIView(AuthenticatedAPIView):
    """저장하지 않은 설정 그대로 대화 한 번을 돌려 본다. 승인 필요 도구는 시뮬레이션만 한다."""

    def post(self, request):
        serializer = BuilderTestRunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        account_id = request.user.account_id

        try:
            team_id = AccountRepository.team_id(account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        draft = {
            "team_id": team_id,
            "instruction": data["instruction"],
            "model": data.get("model"),
            "reasoning_effort": data.get("reasoning_effort"),
            "max_iterations": data.get("max_iterations"),
            "tool_refs": data["tool_refs"],
        }

        return StreamingHttpResponse(
            _builder_test_events(draft=draft, user_input=data["user_input"], account_id=account_id),
            content_type="application/x-ndjson",
        )


class AgentBuilderToolCheckAPIView(AuthenticatedAPIView):
    """선택한 도구 전부를 모델 판단 없이 순서대로 직접 불러 본다."""

    def post(self, request):
        serializer = BuilderToolCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        account_id = request.user.account_id

        try:
            team_id = AccountRepository.team_id(account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        results = check_tools(
            team_id=team_id,
            account_id=account_id,
            tool_refs=data["tool_refs"],
            arguments_by_ref=data["arguments"],
        )
        return Response({"results": results})


class AgentBuilderInstructionRecheckAPIView(AuthenticatedAPIView):
    """사용자가 1단계 보정안을 보고 지시문만 고쳤을 때, 지시문만 빠르게 다시 확인한다.

    description은 다시 안 본다 — 안 건드렸다면 다시 볼 이유가 없다. 이름·설명까지
    포함한 전체 1단계(`build/check/`)보다 가볍고 빠르다.
    """

    def post(self, request):
        serializer = BuilderInstructionRecheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        account_id = request.user.account_id

        try:
            result = review_instruction(
                instruction=data["instruction"],
                tool_refs=data["tool_refs"],
                catalog=_tool_catalog(account_id),
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        except PipelineConfigurationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(builder_instruction_recheck_response(result))


class AgentActivateAPIView(AuthenticatedAPIView):
    """DRAFT/DISABLED → ACTIVE. Chat 위임과 관리 화면의 "Chat에서 사용"에 노출되려면
    거쳐야 하는 문이다.

    **DB에 저장된 값으로 다시 검증한다.** 화면이 "나 아까 통과했음"이라고 보내는
    값을 믿지 않는다 — 그 사이 다른 탭에서 지시문을 고쳤을 수 있고, 활성화
    시점의 실제 내용이 기준이어야 한다.
    """

    def post(self, request, agent_id):
        account_id = request.user.account_id
        try:
            agent = AgentCrudRepository.get(agent_id=agent_id, account_id=account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        try:
            result = _run_builder_check(
                account_id=account_id,
                name=agent["name"],
                description=agent["description"] or "",
                behavior=agent["instruction"] or "",
                tool_refs=agent["tool_refs"],
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        except (PipelineConfigurationError, ValueError):
            # 검증 서비스 자체가 죽었다고 활성화를 막지 않는다 — 그건 배포 사고다.
            # `reject` 게이트는 검증이 실제로 도는 경우에만 의미가 있다.
            logger.warning("활성화 시점 검증을 건너뜁니다(검증 서비스 실패): %s", agent_id)
            result = None

        if result is not None and result.overall == "reject":
            return Response(
                {
                    "detail": result.reject_reason
                    or "설명 또는 지시문 내용이 부족해 활성화할 수 없습니다.",
                    "overall": result.overall,
                },
                status=status.HTTP_409_CONFLICT,
            )

        try:
            row = AgentCrudRepository.set_status(
                agent_id=agent_id, account_id=account_id, status="ACTIVE"
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(agent_response(row))


class AgentDisableAPIView(AuthenticatedAPIView):
    """ACTIVE → DISABLED. 검증 없이 바로 내린다 — 끄는 쪽은 항상 안전하다."""

    def post(self, request, agent_id):
        try:
            row = AgentCrudRepository.set_status(
                agent_id=agent_id, account_id=request.user.account_id, status="DISABLED"
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(agent_response(row))
