"""Agent CRUD API — Builder 가 쓴다 (개발지시_3차 단계 2)."""

import psycopg
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import BearerTokenAuthentication
import logging

from backend.db.agent_platform import AgentCrudRepository, AgentRepository, CustomModelRepository
from backend.db.errors import (
    PermissionDenied,
    RecordNotFound,
    ReferenceNotFound,
    RepositoryError,
)

from .serializers import (
    AGENT_MODELS,
    AgentWriteSerializer,
    MainModelSerializer,
    CustomModelSerializer,
    agent_response,
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

        # 기본 제공이거나, 이 팀이 등록한 커스텀이어야 한다. 아무 문자열이나
        # 받으면 실행 시점에 404 로 죽고 사람은 이유를 모른다.
        try:
            customs = {row["model"] for row in CustomModelRepository.list_for_account(request.user.account_id)}
        except (RepositoryError, psycopg.Error):
            customs = set()
        if model not in AGENT_MODELS and model not in customs:
            return Response(
                {"detail": f"{model} 은 고를 수 없는 모델입니다."}, status=status.HTTP_400_BAD_REQUEST
            )

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
