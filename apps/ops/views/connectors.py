"""연결 서비스 현황 API. 읽기 전용이라 입력값이 없고, 인증 예외는 `AdminView`가
공통으로 처리한다(섹션 1과 동일). 실제 재연결은 계정 소유자가 설정 화면에서
하므로 이 API에는 쓰기 작업이 없다."""

import psycopg
from rest_framework.response import Response

from backend.api_errors import to_response
from backend.db import OpsConnectorRepository

from ..authentication import AdminView
from ..serializers import connector_row_response


class ConnectorListView(AdminView):
    def get(self, request):
        try:
            rows = OpsConnectorRepository.list()
        except psycopg.Error as exc:
            return to_response(exc)
        return Response([connector_row_response(row) for row in rows])
