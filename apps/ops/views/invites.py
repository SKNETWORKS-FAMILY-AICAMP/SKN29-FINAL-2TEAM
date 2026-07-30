"""계정 연결·초대 현황 API.

목록 조회는 입력값이 없고, 폐기·연결해제는 본문 없이 초대 ID만으로 동작한다.
도메인 예외(폐기할 수 없는 상태, 존재하지 않는 초대, 연결된 적 없는 초대)는
`Repository`가 던지고 `to_response()`가 상태 코드로 변환한다.
"""

import psycopg
from rest_framework.response import Response

from backend.api_errors import to_response
from backend.db import OpsInviteRepository
from backend.db.errors import RepositoryError

from ..authentication import AdminView


class InviteListView(AdminView):
    def get(self, request):
        try:
            rows = OpsInviteRepository.list()
        except psycopg.Error as exc:
            return to_response(exc)
        return Response(rows)


class InviteDiscardView(AdminView):
    def post(self, request, invite_id):
        try:
            result = OpsInviteRepository.discard(invite_id=invite_id, actor_account_id=request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(result)


class InviteUnlinkView(AdminView):
    def post(self, request, invite_id):
        try:
            result = OpsInviteRepository.unlink_by_invite(
                invite_id=invite_id,
                actor_account_id=request.user.account_id,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(result)
