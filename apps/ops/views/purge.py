"""완전 삭제 — 팀·계정을 실제로 지운다. 되돌릴 수 없다.

잠금(`AccountLockView`)과 나란히 두지 않고 파일을 따로 둔다 — 잠금은 되돌릴 수
있고 이건 아니다. 나중에 이 파일을 열었을 때 "여기 있는 건 전부 영구적이다"가
한눈에 보여야 한다.

미리보기(GET)와 실행(DELETE)을 같은 주소에 둔다. 화면은 모달을 열 때 GET 으로
「무엇이 몇 건 지워지는지」를 받아 그리고, 사람이 이름을 그대로 입력하면 DELETE 로
보낸다.
"""

import psycopg
from rest_framework.response import Response

from backend.api_errors import to_response
from backend.db import OpsPurgeRepository
from backend.db.errors import RepositoryError

from ..authentication import AdminView
from ..serializers import PurgeConfirmSerializer


class TeamPurgeView(AdminView):
    def get(self, request, team_id):
        try:
            return Response(OpsPurgeRepository.team_preview(team_id=team_id))
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)

    def delete(self, request, team_id):
        serializer = PurgeConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = OpsPurgeRepository.purge_team(
                team_id=team_id,
                actor_account_id=request.user.account_id,
                confirm_name=serializer.validated_data["confirm_name"],
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(result)


class AccountPurgeView(AdminView):
    def get(self, request, account_id):
        try:
            return Response(OpsPurgeRepository.account_preview(account_id=account_id))
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)

    def delete(self, request, account_id):
        serializer = PurgeConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = OpsPurgeRepository.purge_account(
                account_id=account_id,
                actor_account_id=request.user.account_id,
                confirm_name=serializer.validated_data["confirm_name"],
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(result)
