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
from services.harness import check_tools, run_agent

from .serializers import (
    AGENT_MODELS,
    AgentVersionPublishSerializer,
    AgentWriteSerializer,
    BuilderTestRunSerializer,
    BuilderToolCheckSerializer,
    agent_response,
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


def _split(data: dict) -> tuple[dict, list[str]]:
    fields = dict(data)
    return fields, fields.pop("tool_refs")


def _model_rejection(account_id: str, model: str | None) -> Response | None:
    """이 팀이 고를 수 있는 모델인가. 괜찮으면 `None`, 아니면 그대로 돌려줄 응답.

    **고를 수 있는 목록은 팀마다 다르다.** 기본 제공 6종에 더해, 그 팀이 Model 탭에서
    등록한 커스텀 모델 API 가 있다. 그래서 serializer 의 `ChoiceField` 로는 못 막고
    (팀을 모른다) 여기서 대조한다.

    아무 문자열이나 받으면 저장은 되고 **실행 시점에 404 로 죽는다** — 사람은 화면에
    저장됐다고 떴으니 맞다고 믿는다. 조용히 실패하는 그 경로를 여기서 끊는다.

    기본 제공이면 **DB 를 아예 보지 않는다.** 커스텀 목록을 못 읽는다고 luna 조차 못
    고르게 되면 안 되고, 못 읽었을 때 「고를 수 없는 모델」이라고 말하는 것은 거짓말이라
    그때는 503 으로 그 사실을 그대로 알린다.
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
        rejection = _model_rejection(request.user.account_id, fields.get("model"))
        if rejection is not None:
            return rejection
        blocker = _check_tool_refs(account_id=request.user.account_id, tool_refs=tool_refs)
        if blocker is not None:
            return Response({"detail": blocker}, status=status.HTTP_400_BAD_REQUEST)
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
        rejection = _model_rejection(request.user.account_id, fields.get("model"))
        if rejection is not None:
            return rejection
        blocker = _check_tool_refs(account_id=request.user.account_id, tool_refs=tool_refs)
        if blocker is not None:
            return Response({"detail": blocker}, status=status.HTTP_400_BAD_REQUEST)
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


#: 메인 모델은 **팀이 한 번 정하는 값**이라(아래 docstring) 한 사람이 바꾸면 팀
class CustomModelAPIView(AuthenticatedAPIView):
    """이 팀에 등록된 모델 API. **읽기 전용이다.**

    등록하고 지우는 것은 운영자 콘솔(`/api/ops/models/`)이 한다 — 회사가 요청하면
    우리가 등록한다(2026-08-13 멘토링). 예전에는 여기에 POST·DELETE 와 모델 목록
    조회(probe)가 있었는데 함께 걷어냈다. **화면에서만 감추면 규칙이 아니다** —
    쓰기 경로가 API 에 남아 있으면 그대로 부를 수 있다.

    팀이 목록은 봐야 한다. 지금 우리 팀이 무엇으로 도는지 아는 것과, 그것을 바꿀
    수 있는 것은 다른 이야기다.

    **키는 절대 돌려주지 않는다.** 이름·주소·모델만 준다.
    """

    def get(self, request):
        try:
            return Response(CustomModelRepository.list_for_account(request.user.account_id))
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)


def _tool_catalog(account_id: str) -> dict[str, dict]:
    """빌더가 선택할 수 있는 도구 전체(내장 + 팀 MCP) — `tool_ref`로 찾아본다."""

    mcp = AgentCrudRepository.team_tool_refs(account_id)
    return {row["tool_ref"]: row for row in builtin_tool_response() + mcp_tool_response(mcp)}


def _check_tool_refs(*, account_id: str, tool_refs: list[str]) -> str | None:
    """`AgentListCreateAPIView`/`AgentDetailAPIView`/`AgentActivateAPIView`가 함께 쓰는
    구조 검증 — 도구 참조가 실제로 존재하는지, 중복 선택은 없는지만 본다."""

    return check_definition(tool_refs=tool_refs, catalog=_tool_catalog(account_id))


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

        rejection = _model_rejection(account_id, data.get("model"))
        if rejection is not None:
            return rejection

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


class AgentActivateAPIView(AuthenticatedAPIView):
    """DRAFT/DISABLED → ACTIVE. Chat 위임과 관리 화면의 "Chat에서 사용"에 노출되려면
    거쳐야 하는 문이다.

    **DB에 저장된 값으로 다시 검증한다.** 화면이 "나 아까 통과했음"이라고 보내는
    값을 믿지 않는다 — 그 사이 다른 탭에서 도구 구성을 바꿨을 수 있고, 활성화
    시점의 실제 내용이 기준이어야 한다.

    **모델도 그 「그 사이」에 사라질 수 있다.** 저장할 때는 있던 커스텀 모델을 팀이
    Model 탭에서 지우면, 그걸 쓰던 초안은 아무 표시 없이 남는다. 화면은 활성화할 때
    본문을 다시 보내지 않으므로(`activateAgent` 는 빈 POST 다) 여기서 안 보면 아무도
    안 본다 — 「활성화했습니다」를 띄운 뒤 첫 대화에서 죽는다.
    """

    def post(self, request, agent_id):
        account_id = request.user.account_id
        try:
            agent = AgentCrudRepository.get(agent_id=agent_id, account_id=account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        rejection = _model_rejection(account_id, agent.get("model"))
        if rejection is not None:
            return rejection

        blocker = _check_tool_refs(account_id=account_id, tool_refs=agent["tool_refs"])
        if blocker is not None:
            return Response({"detail": blocker}, status=status.HTTP_409_CONFLICT)

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


# =========================================================================
# 새 버전 스키마(agents/agent_versions) — services/agent_runtime/ 전용.
#
# 위 옛 엔드포인트와 나란히 존재한다. apps/chat·apps/agents의 실행 경로는
# 아직 이 스키마를 모른다(services/agent_runtime/이 미완성 — loader.py가
# NotImplementedError). 지금은 저장·조회만 가능하고, 실행에 실제로 쓰이는
# 것은 harness 경로의 `agent` 테이블뿐이다. 배경:
# docs/작업기록/Deep_Agents/2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md
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
            # `_check_tool_refs`가 팀 소속을 다시 확인하는 과정에서
            # `PermissionDenied`(팀 없는 계정) 등을 낼 수 있다 — 옛
            # `AgentListCreateAPIView.post()`는 이 호출을 try/except 밖에 둬서
            # 그 경우 500으로 새는 잠재 버그가 있었다(2026-08-13 검증 중 발견).
            # 여기서는 감싼다.
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

        **일반적인 PUT과 달리 멱등하지 않다.** `agent_versions`가 불변이라
        "덮어쓰기"가 없다 — 같은 바디로 두 번 호출하면 버전이 두 개 생기고
        `current_version_id`만 최신 것으로 옮겨간다(02 §5.2). 옛 버전을 이미
        고정 참조하는 세션·부모 에이전트는 그대로 이전 버전을 계속 쓴다.
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
        return Response(agent_version_response(row))


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
        return Response(agent_version_response(row))


class AgentVersionDisableAPIView(AuthenticatedAPIView):
    """ACTIVE → DISABLED. 검증 없이 바로 내린다 — 끄는 쪽은 항상 안전하다."""

    def post(self, request, agent_id):
        try:
            row = AgentVersionCrudRepository.set_status(
                agent_id=agent_id, account_id=request.user.account_id, status="DISABLED"
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(agent_version_response(row))
