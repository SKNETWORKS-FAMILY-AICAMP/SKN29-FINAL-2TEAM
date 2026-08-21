"""사용 현황 API. 조회 전용이라 입력값이 없고, 인증 예외는 `AdminView`가
공통으로 처리한다(섹션 1과 동일).

**관측성의 「요약」 층이다**(2026-08-21). 실행 이력은 2026-08-13 부터 쌓이고
있었는데 집계해 보여주는 자리가 없었다 — 팀 상세의 「최근 실행」 표가 유일한
노출이고 그마저 옛 에이전트 표만 조인해 한 줄도 안 나온다.

실행 하나를 따라가는 「상세 트레이스」는 여기서 만들지 않는다. Langfuse 로
보낸다(`services/agent_runtime/tracing/callbacks.py`) — watsonx Orchestrate 도
같은 구성이고, 표준 규격으로 뱉어 기성 도구에 꽂는 것이 이 층의 업계 관행이다.
"""

import psycopg
from rest_framework.response import Response

from backend.api_errors import to_response
from backend.db import OpsUsageRepository

from ..authentication import AdminView


class UsageView(AdminView):
    def get(self, request):
        try:
            summary = OpsUsageRepository.summary()
        except psycopg.Error as exc:
            return to_response(exc)
        return Response(summary)
