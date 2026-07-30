"""운영 현황 요약 API. 조회 전용이라 입력값이 없고, 인증 예외는 `AdminView`가
공통으로 처리한다(만료·위조 토큰, 권한 회수 등 — 섹션 1과 동일)."""

import psycopg
from rest_framework.response import Response

from backend.api_errors import to_response
from backend.db import OpsOverviewRepository

from ..authentication import AdminView


class OverviewView(AdminView):
    def get(self, request):
        try:
            summary = OpsOverviewRepository.summary()
        except psycopg.Error as exc:
            return to_response(exc)
        return Response(summary)
