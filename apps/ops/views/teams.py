"""팀 현황 API. 조회 전용이라 입력값이 없고, 인증 예외는 `AdminView`가
공통으로 처리한다(섹션 1과 동일).

운영자가 보는 단위는 HR 조직도가 아니라 팀이다 — 우리 플랫폼을 쓰는 것이
팀이고, 조직도는 고객사 내부 사정이라 알 필요가 없다.
"""

import psycopg
from rest_framework.response import Response

from backend.api_errors import to_response
from backend.db import OpsTeamRepository

from ..authentication import AdminView


class TeamsView(AdminView):
    def get(self, request):
        try:
            teams = OpsTeamRepository.list_with_stats()
        except psycopg.Error as exc:
            return to_response(exc)
        return Response(teams)
