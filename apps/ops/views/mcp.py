"""팀별 Customizing Tool(MCP·FastAPI 서버) 등록·연결 확인·삭제.

**팀이 스스로 등록하지 않는다.** 요청을 받으면 운영자가 등록한다(2026-08-18
멘토링). 설정 화면의 등록 폼은 없앴다 — 붙이려면 https 주소와 인증 토큰을
알아야 하는데, 그건 「코딩 없이」를 내세운 제품이 비개발자에게 요구할 일이
아니다. 8/13 에 모델로 이미 같은 길을 밟았다(`views/models.py`).

**권한 범위는 여전히 팀이다.** 등록하는 사람만 운영자로 바뀔 뿐, 그 서버의
도구를 에이전트에 붙여 쓰는 것은 그 팀뿐이다(`mcp_server.team_id`).
"""

import logging

import psycopg
from rest_framework import status
from rest_framework.response import Response

from apps.mcp.serializers import server_response
from backend.api_errors import to_response
from backend.db import log_audit
from backend.db.agent_platform import McpServerRepository
from backend.db.errors import RepositoryError
from services.mcp import McpError, UnsafeEndpoint, initialize_and_list_tools, validate

from ..authentication import AdminView
from ..serializers import OpsMcpRegisterSerializer, OpsMcpUpdateSerializer, ops_mcp_row_response

logger = logging.getLogger(__name__)


class McpListCreateView(AdminView):
    def get(self, request):
        try:
            rows = McpServerRepository.list_all()
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response([ops_mcp_row_response(row) for row in rows])

    def post(self, request):
        """등록. **주소 검사가 저장보다 먼저다**(11_MCP_설계 §4-1).

        저장한 뒤에 검사하면 위험한 주소가 DB 에 남는다 — 나중에 검사가
        느슨해지면 그 행들이 그대로 살아난다. 운영자가 넣는다고 사정이 다르지
        않다: 주소는 고객에게 전달받아 옮겨 적는 값이다.
        """

        serializer = OpsMcpRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            endpoint_url = validate(data["endpoint_url"])
        except UnsafeEndpoint as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            row = McpServerRepository.create(
                team_id=data["team_id"],
                name=data["name"],
                endpoint_url=endpoint_url,
                auth_token=(data.get("auth_token") or "").strip() or None,
                registered_by=request.user.account_id,
            )
            # 남의 팀에 외부 호출 경로를 심는 일이라 반드시 기록에 남는다.
            # **토큰은 남기지 않는다** — 감사 로그는 나중에 사람이 읽는 표다.
            log_audit(
                actor_account_id=request.user.account_id,
                action="OPS_MCP_REGISTER",
                target_type="TEAM",
                target_id=data["team_id"],
                payload={"mcp_server_id": row["mcp_server_id"], "name": data["name"],
                         "endpoint_url": endpoint_url},
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(server_response(row), status=status.HTTP_201_CREATED)


class McpDetailView(AdminView):
    def patch(self, request, server_id):
        """고친다. **주소 검사는 등록과 같은 자리에서 한다**(§4-1) — 고칠 때만
        건너뛰면 등록에서 막은 주소가 수정으로 들어온다."""

        serializer = OpsMcpUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            endpoint_url = validate(data["endpoint_url"])
        except UnsafeEndpoint as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            row = McpServerRepository.update(
                server_id=server_id,
                team_id=data["team_id"],
                name=data["name"],
                endpoint_url=endpoint_url,
                auth_token=(data.get("auth_token") or "").strip() or None,
                replace_token=data["replace_token"],
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(server_response(row))

    def delete(self, request, server_id):
        team_id = (request.query_params.get("team_id") or "").strip()
        if not team_id:
            return Response({"detail": "팀이 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            McpServerRepository.delete(server_id=server_id, team_id=team_id)
            # **무엇을 지웠는지 남긴다.** 행을 지우고 나면 server_id 는 아무것도
            # 가리키지 않아서, 그 값만 남기면 나중에 복원할 수 없다. 등록 쪽과
            # 같은 모양으로 맞춘다.
            log_audit(
                actor_account_id=request.user.account_id,
                action="OPS_MCP_REMOVE",
                target_type="TEAM",
                target_id=team_id,
                payload={"mcp_server_id": server_id},
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class McpTestView(AdminView):
    """연결 확인 — initialize + tools/list 로 도구 목록을 받아 저장한다.

    **실패해도 등록은 남기고 ERROR 로 표시한다**(설계 §3). 주소나 토큰을 고쳐
    다시 시도할 값이고, 상태를 보여 줘야 왜 그 팀의 에이전트 편집 화면에서 이
    서버의 도구를 못 고르는지 알 수 있다.
    """

    def post(self, request, server_id):
        team_id = (request.data.get("team_id") or "").strip()
        if not team_id:
            return Response({"detail": "팀이 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            server = McpServerRepository.credentials(server_id=server_id, team_id=team_id)
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)

        try:
            tools = initialize_and_list_tools(
                endpoint_url=server["endpoint_url"], auth_token=server["auth_token"]
            )
        except (McpError, UnsafeEndpoint) as exc:
            # 토큰이 섞여 들어갈 수 있는 자리라 예외 문자열을 그대로 로그에
            # 남기지 않는다(§4-2 — 로그에 토큰 금지).
            logger.warning("연결 확인 실패: server=%s (%s)", server_id, exc.__class__.__name__)
            try:
                McpServerRepository.mark_error(server_id=server_id, team_id=team_id)
            except (RepositoryError, psycopg.Error) as db_exc:
                return to_response(db_exc)
            return Response(
                {
                    "status": "ERROR",
                    "error_code": getattr(exc, "code", "unreachable"),
                    "detail": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            saved = McpServerRepository.save_tools(
                server_id=server_id, team_id=team_id, tools=tools
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response({"status": "CONNECTED", "tool_count": saved})
