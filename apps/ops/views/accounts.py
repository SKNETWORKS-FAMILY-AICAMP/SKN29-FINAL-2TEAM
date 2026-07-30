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
from ..serializers import account_row_response


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
