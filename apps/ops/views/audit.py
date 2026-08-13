"""감사 로그 API. 읽기 전용이라 입력값이 없고, 인증 예외는 `AdminView`가 공통으로
처리한다(섹션 1과 동일).

전에는 엔드포인트가 다섯이었다 — 「분석·결정 기록」 4종(배정 실행·추천 결과·검증
결과·PM 결정)이 함께 있었고 **넷 다 항상 빈 목록**이었다. 그 테이블에 쓰는 추천
파이프라인이 이 저장소에 없고 제품도 업무 배정 추천에서 물러나서, 화면과 함께
걷었다(2026-08-13). 되살릴 일이 생기면 git 이력에 있다.
"""

import psycopg
from rest_framework.response import Response

from backend.api_errors import to_response
from backend.db import OpsAuditRepository

from ..authentication import AdminView


class OperationLogView(AdminView):
    def get(self, request):
        try:
            rows = OpsAuditRepository.list_operations()
        except psycopg.Error as exc:
            return to_response(exc)
        return Response(rows)
