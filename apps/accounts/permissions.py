"""역할 문지기.

**화면이 버튼을 감추는 것은 문지기가 아니다.** 설정의 「권한」 탭이 「팀장만」이라고
선언한 네 가지 중 실제로 서버가 막던 것은 커넥터 연결 하나뿐이었고, 나머지 셋(팀원
초대·명부 관리·MCP 서버 등록·팀 업무량 기준)은 API 를 직접 부르면 그대로 통과했다
(2026-08-13 확인). 표가 지켜지지 않는 약속을 하고 있었다 — **틀린 권한 표는 없는
표보다 나쁘다.**

역할 판정은 `account_role` 하나뿐이다(가입 경로로 정한다). 여기서는 그것을 쓰는
자리만 만든다.

`apps/connectors` 는 이 함수를 쓰지 않는다 — 그쪽은 검사 뒤에 `profile` 을 계속
쓰기 때문에 프로필을 한 번 더 읽지 않으려고 자기 자리에서 검사한다. 규칙 자체는
같은 `account_role` 을 본다.
"""

from typing import Any

import psycopg
from rest_framework import status
from rest_framework.response import Response

from backend.db import AccountRepository
from backend.db.errors import RepositoryError

from .serializers import account_role


def require_leader(account_id: str, detail: str) -> Response | None:
    """팀장이 아니면 403 응답을, 팀장이면 `None` 을 돌려준다.

    호출부는 `if (denied := require_leader(...)): return denied` 로 쓴다 —
    돌려주는 것이 있으면 그대로 응답하고, 없으면 하던 일을 계속한다.

    프로필을 못 읽는 것은 권한 거절이 아니라 **서버 사정**이라 그대로 올린다.
    거절과 장애를 같은 코드로 뭉개면 「내가 권한이 없나」와 「지금 서버가 이상한가」를
    사용자가 구별할 수 없다.
    """

    try:
        profile: dict[str, Any] = AccountRepository.get_profile(account_id)
    except (RepositoryError, psycopg.Error) as exc:
        return Response(
            {"detail": "데이터베이스 요청을 처리할 수 없습니다.", "error": exc.__class__.__name__},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    if account_role(profile) != "leader":
        return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)
    return None


def require_owner_or_leader(account_id: str, owner_account_id: str | None, detail: str) -> Response | None:
    """만든 사람이거나 팀장이 아니면 403 응답을, 맞으면 `None`을 돌려준다.

    `require_leader`와 같은 호출 관례: `if (denied := require_owner_or_leader(...)): return denied`.
    본인 소유면 프로필을 읽을 필요도 없이 바로 통과시킨다 — 그 경우까지
    `require_leader`를 부르면 팀장이 아닌 소유자가 자기 것을 못 지우게 된다.
    """

    if account_id == owner_account_id:
        return None
    return require_leader(account_id, detail)
