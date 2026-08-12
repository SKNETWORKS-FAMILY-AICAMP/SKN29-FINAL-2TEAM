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
from backend.db.agent_platform import AgentCrudRepository, AgentRepository, CustomModelRepository
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
    AGENT_MODELS,
    AgentWriteSerializer,
    BuilderCheckSerializer,
    BuilderInstructionRecheckSerializer,
    BuilderTestRunSerializer,
    BuilderToolCheckSerializer,
    CustomModelSerializer,
    MainModelSerializer,
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


class MainModelAPIView(AuthenticatedAPIView):
    """이 팀의 **메인 모델** — 오케스트레이션하는 정문 에이전트가 쓰는 모델.

    Chat 은 정문에게 말하고, 정문이 필요하면 팀 에이전트에게 넘긴다. 그래서
    「대화가 어떤 모델로 도는가」는 정문의 모델이고, 그것은 **팀이 한 번 정하는
    값**이다 — 개별 에이전트의 모델은 그 에이전트를 만들 때 각자 고른다.

    저장 자리를 `team` 에 새로 만들지 않고 정문 에이전트의 `model` 을 그대로
    쓴다. 스키마를 바꾸면 팀원 전원이 ALTER 를 돌려야 하는데, 여기서 정하려는
    값이 실제로 그 에이전트의 모델이라 새 칸을 만들 이유가 없다.
    """

    def get(self, request):
        try:
            row = AgentRepository.main_model(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        # 정문이 없으면 「없다」고 말한다. 임의의 기본값을 저장된 것처럼 보이면 안 된다.
        return Response({"model": row["model"] if row else None, "agent_name": row["name"] if row else None})

    def put(self, request):
        serializer = MainModelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        model = serializer.validated_data["model"]

        rejection = _model_rejection(request.user.account_id, model)
        if rejection is not None:
            return rejection

        try:
            row = AgentRepository.set_main_model(account_id=request.user.account_id, model=model)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response({"model": row["model"], "agent_name": row["name"]})


class CustomModelAPIView(AuthenticatedAPIView):
    """팀이 직접 등록한 모델 API 목록.

    **키는 절대 돌려주지 않는다.** 이름·주소·모델만 준다 — 화면에 다시 보여줄
    이유가 없고, 보여주면 그 화면이 유출 경로가 된다(MCP 토큰과 같은 규칙).
    """

    def get(self, request):
        try:
            return Response(CustomModelRepository.list_for_account(request.user.account_id))
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

    def post(self, request):
        serializer = CustomModelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # **같은 팀에 같은 모델 이름을 두 번 두지 않는다.** serializer 는 기본 제공
        # 이름만 막는다 — 팀이 이미 뭘 등록했는지는 여기서만 안다.
        #
        # 경로가 모델 이름 하나로 정해지므로(`for_model`), 이름이 겹치면 실행은
        # **먼저 등록한 것으로 고정된다**. 화면에는 출처가 달라 둘로 보이니, 회사
        # 키를 골랐는데 개인 키로 도는 일이 조용히 난다. 키를 나누려고 만든 기능이
        # 바로 그 지점에서 깨진다.
        try:
            taken = {row["model"] for row in CustomModelRepository.list_for_account(request.user.account_id)}
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        if data["model"] in taken:
            return Response(
                {"detail": f"{data['model']} 은 이미 등록돼 있습니다. 지우고 다시 등록하세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # **저장 전에 한 번 써 본다.** 안 되는 것을 받아 두면 그 팀의 대화가
        # 조용히 실패하고, 사람은 저장이 됐으니 맞다고 믿는다.
        error = _verify_model_key(data["api_key"], data["base_url"], data["model"])
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        try:
            CustomModelRepository.add(
                account_id=request.user.account_id,
                label=data["label"],
                base_url=data["base_url"],
                api_key=data["api_key"],
                model=data["model"],
            )
            return Response(
                CustomModelRepository.list_for_account(request.user.account_id),
                status=status.HTTP_201_CREATED,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

    def delete(self, request):
        conn_id = request.query_params.get("conn_id") or ""
        try:
            CustomModelRepository.remove(account_id=request.user.account_id, conn_id=conn_id)
            return Response(CustomModelRepository.list_for_account(request.user.account_id))
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)


class CustomModelProbeAPIView(AuthenticatedAPIView):
    """주소와 키를 주면 **그 엔드포인트가 가진 모델 목록**을 돌려준다.

    사람이 모델 이름을 외워 적게 하지 않는다. 다만 목록을 안 주는 구현도 흔해서
    (Anthropic 호환 경로는 401 이다) 실패하면 빈 목록과 이유를 준다 — 그때는
    화면이 직접 입력을 받는다.
    """

    def post(self, request):
        base_url = (request.data.get("base_url") or "").strip()
        api_key = (request.data.get("api_key") or "").strip()
        if not base_url or not api_key:
            return Response({"detail": "주소와 키가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=base_url, timeout=20, max_retries=0)
            names = sorted(item.id for item in client.models.list().data)
        except Exception as exc:  # noqa: BLE001 - 어떤 실패든 「여기서는 못 고른다」다
            logger.info("모델 목록 조회 실패: %s", type(exc).__name__)
            return Response(
                {
                    "models": [],
                    # **이름을 직접 적게 하지 않는다.** 외워 적게 하면 오타 하나가
                    # 실행 시점 404 가 되고, 그건 「코딩 없이」를 내세운 제품이
                    # 사용자에게 떠넘기는 일이다(2026-08-12 PM 지적).
                    "detail": "이 주소에서 모델 목록을 받지 못했습니다. 주소와 키를 확인해 주세요.",
                }
            )
        if not names:
            return Response({"models": [], "detail": "이 주소가 쓸 수 있는 모델을 알려주지 않았습니다."})
        return Response({"models": names, "detail": None})


def _verify_model_key(api_key: str, base_url: str = "", model: str = "") -> str | None:
    """실제로 부를 수 있는가. 되면 `None`, 아니면 사람에게 보여줄 이유.

    주소를 직접 넣은 경우에는 **그 모델로 한 번 답을 받아 본다** — 목록 조회만
    되고 호출은 안 되는 엔드포인트가 흔하다.
    """

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url or None, timeout=25, max_retries=0)
        if base_url:
            client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": "hi"}]
            )
        else:
            client.models.list()
    except Exception as exc:  # noqa: BLE001 - 어떤 실패든 「이걸로는 못 부른다」다
        logger.warning("모델 키 확인 실패: %s", type(exc).__name__)
        if base_url:
            return "이 주소와 모델로 답을 받지 못했습니다. 주소·키·모델 이름을 확인해 주세요."
        return "이 키로 모델을 부르지 못했습니다. 키가 맞는지, 결제가 설정돼 있는지 확인해 주세요."
    return None


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
