"""연결 서비스 현황 API.

오래 읽기 전용이었다 — 재연결은 계정 소유자가 설정에서 하므로 운영자가 할 일이
없다고 봤다. 그런데 **끊는 쪽은 아무도 못 했다.** 토큰이 샜거나 엉뚱한 계정으로
연결된 것을 즉시 끊을 방법이 제품 어디에도 없어서, 그것만 여기에 연다
(2026-08-13 PM 요청). 여전히 연결하는 것은 이 콘솔의 일이 아니다.
"""

import psycopg
from rest_framework.response import Response

from backend.api_errors import to_response
from backend.db import OpsConnectorRepository
from backend.db.errors import RepositoryError

from ..authentication import AdminView
from ..serializers import ConnectorRevokeSerializer, connector_row_response


class ConnectorListView(AdminView):
    def get(self, request):
        try:
            rows = OpsConnectorRepository.list()
        except psycopg.Error as exc:
            return to_response(exc)
        return Response([connector_row_response(row) for row in rows])


class ConnectorDetailView(AdminView):
    def get(self, request, conn_id):
        try:
            row = OpsConnectorRepository.get(conn_id)
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(connector_row_response(row))


class ConnectorRevokeView(AdminView):
    """연결 강제 해제. 대상이 무엇인지(People DB·등록 모델은 안 됨)와 이미 해제된
    연결인지는 `Repository`가 트랜잭션 안에서 본다 — 화면에서만 막으면 규칙이 아니다."""

    def post(self, request, conn_id):
        serializer = ConnectorRevokeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = OpsConnectorRepository.revoke(
                conn_id=conn_id,
                actor_account_id=request.user.account_id,
                reason=serializer.validated_data["reason"],
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(result)
