"""계정 연결·초대 현황 API.

목록 조회는 입력값이 없고, 폐기·연결해제는 **사유만** 본문으로 받는다(대상은
경로에 있다). 도메인 예외(폐기할 수 없는 상태, 존재하지 않는 초대, 연결된 적
없는 초대)는 `Repository`가 던지고 `to_response()`가 상태 코드로 변환한다.
"""

import psycopg
from rest_framework.response import Response

from backend.api_errors import to_response
from backend.db import OpsInviteRepository
from backend.db.errors import RepositoryError

from ..authentication import AdminView
from ..serializers import ReasonSerializer


def _reason(request) -> str:
    serializer = ReasonSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data["reason"]


class InviteListView(AdminView):
    def get(self, request):
        try:
            rows = OpsInviteRepository.list()
        except psycopg.Error as exc:
            return to_response(exc)
        return Response(rows)


class InviteDetailView(AdminView):
    """초대 한 건. 상세가 별도 페이지가 되면서 생긴 경로다."""

    def get(self, request, invite_id):
        try:
            row = OpsInviteRepository.get(invite_id)
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        # 목록과 같은 모양으로 돌려준다 — 여기만 다른 표현을 쓰면 화면 둘이 어긋난다.
        return Response(row)


class InviteDiscardView(AdminView):
    def post(self, request, invite_id):
        try:
            result = OpsInviteRepository.discard(
                invite_id=invite_id,
                actor_account_id=request.user.account_id,
                reason=_reason(request),
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(result)


class InviteUnlinkView(AdminView):
    def post(self, request, invite_id):
        try:
            result = OpsInviteRepository.unlink_by_invite(
                invite_id=invite_id,
                actor_account_id=request.user.account_id,
                reason=_reason(request),
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(result)
