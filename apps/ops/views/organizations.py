"""연결 조직 현황 API. 조회 전용이라 입력값이 없고, 인증 예외는 `AdminView`가
공통으로 처리한다(섹션 1과 동일)."""

import psycopg
from rest_framework.response import Response

from backend.api_errors import to_response
from backend.db import OpsOrganizationRepository

from ..authentication import AdminView


class OrganizationsView(AdminView):
    def get(self, request):
        try:
            organizations = OpsOrganizationRepository.list_with_stats()
        except psycopg.Error as exc:
            return to_response(exc)
        return Response(organizations)
