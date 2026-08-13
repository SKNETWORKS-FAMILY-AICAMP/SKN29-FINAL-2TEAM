"""계정 관리 API.

목록 조회는 입력값이 없다. 상태를 바꾸는 조치는 **사유만** 본문으로 받는다 —
대상은 이미 URL 경로에 있다. 도메인 예외(존재하지 않는 계정, 탈퇴한 계정, 본인
계정 잠금 시도, 이미 처리된 상태, 연결된 직원 없음)는 `Repository`가 던지고
`to_response()`가 상태 코드로 변환한다.
"""

import psycopg
from rest_framework.response import Response

from backend.api_errors import to_response
from backend.db import OpsAccountRepository
from backend.db.errors import RepositoryError

from ..authentication import AdminView
from ..serializers import AdminGrantSerializer, ReasonSerializer, account_row_response


def _reason(request) -> str:
    """본문에서 사유만 꺼낸다. 본문이 없어도 통과한다(빈 사유)."""

    serializer = ReasonSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data["reason"]


class AccountListView(AdminView):
    def get(self, request):
        try:
            rows = OpsAccountRepository.list()
        except psycopg.Error as exc:
            return to_response(exc)
        return Response([account_row_response(row) for row in rows])


class AccountDetailView(AdminView):
    """계정 한 건. 상세가 별도 페이지가 되면서 생긴 경로다.

    예전에는 목록 화면 아래 섹션이라 목록이 이미 들고 있는 값을 그대로 썼다.
    페이지가 갈리면 주소로 바로 들어올 수 있어야 하므로 한 건을 줄 자리가 필요하다.
    """

    def get(self, request, account_id):
        try:
            row = OpsAccountRepository.get(account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(account_row_response(row))


class AccountLockView(AdminView):
    def post(self, request, account_id):
        try:
            result = OpsAccountRepository.lock(
                account_id=account_id,
                actor_account_id=request.user.account_id,
                reason=_reason(request),
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(result)


class AccountUnlockView(AdminView):
    def post(self, request, account_id):
        try:
            result = OpsAccountRepository.unlock(
                account_id=account_id,
                actor_account_id=request.user.account_id,
                reason=_reason(request),
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(result)


class AccountUnlinkPersonView(AdminView):
    def post(self, request, account_id):
        try:
            result = OpsAccountRepository.unlink_all(
                account_id=account_id,
                actor_account_id=request.user.account_id,
                reason=_reason(request),
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(result)


class AccountAdminView(AdminView):
    """운영자 권한 부여·회수.

    잠금과 달리 **본문을 받는다** — 켜는지 끄는지와 사유가 필요하기 때문이다.
    안전장치(자기 권한 불가·마지막 운영자 보호)는 `OpsAccountRepository.set_admin`
    이 트랜잭션 안에서 본다. 화면에서만 막으면 규칙이 아니다.
    """

    def post(self, request, account_id):
        serializer = AdminGrantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = OpsAccountRepository.set_admin(
                account_id=account_id,
                actor_account_id=request.user.account_id,
                is_admin=serializer.validated_data["is_admin"],
                reason=serializer.validated_data["reason"],
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(result)
