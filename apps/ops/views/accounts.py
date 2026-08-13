"""계정 관리 API.

목록 조회는 입력값이 없고, 잠금·잠금해제·연결해제는 본문 없이 계정 ID만으로
동작한다(URL 경로에 이미 대상이 있으므로). 도메인 예외(존재하지 않는 계정,
탈퇴한 계정, 본인 계정 잠금 시도, 이미 처리된 상태, 연결된 직원 없음)는
`Repository`가 던지고 `to_response()`가 상태 코드로 변환한다.
"""

import psycopg
from rest_framework.response import Response

from backend.api_errors import to_response
from backend.db import OpsAccountRepository
from backend.db.errors import RepositoryError

from ..authentication import AdminView
from ..serializers import AdminGrantSerializer, account_row_response


class AccountListView(AdminView):
    def get(self, request):
        try:
            rows = OpsAccountRepository.list()
        except psycopg.Error as exc:
            return to_response(exc)
        return Response([account_row_response(row) for row in rows])


class AccountLockView(AdminView):
    def post(self, request, account_id):
        try:
            result = OpsAccountRepository.lock(account_id=account_id, actor_account_id=request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(result)


class AccountUnlockView(AdminView):
    def post(self, request, account_id):
        try:
            result = OpsAccountRepository.unlock(account_id=account_id, actor_account_id=request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(result)


class AccountUnlinkPersonView(AdminView):
    def post(self, request, account_id):
        try:
            result = OpsAccountRepository.unlink_all(account_id=account_id, actor_account_id=request.user.account_id)
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
