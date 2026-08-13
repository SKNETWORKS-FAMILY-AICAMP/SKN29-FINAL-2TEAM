"""팀 현황 API. 조회 전용이라 입력값이 없고, 인증 예외는 `AdminView`가
공통으로 처리한다(섹션 1과 동일).

운영자가 보는 단위는 HR 조직도가 아니라 팀이다 — 우리 플랫폼을 쓰는 것이
팀이고, 조직도는 고객사 내부 사정이라 알 필요가 없다.
"""

import psycopg
from rest_framework.response import Response

from backend.api_errors import to_response
from backend.db import OpsTeamRepository
from backend.db.errors import RepositoryError

from ..authentication import AdminView
from ..serializers import TeamOwnerTransferSerializer


class TeamsView(AdminView):
    def get(self, request):
        try:
            teams = OpsTeamRepository.list_with_stats()
        except psycopg.Error as exc:
            return to_response(exc)
        return Response(teams)


class TeamOwnerView(AdminView):
    """팀 소유자 이전.

    **팀장이 나가면 그 팀을 아무도 손댈 수 없었다** — `owner_account_id` 를 바꾸는
    경로가 어디에도 없었다. 조회 전용이던 이 화면에 처음 생기는 쓰기다.

    GET 은 넘길 수 있는 후보(그 팀의 살아 있는 계정)를 준다. 화면이 계정 전체
    목록에서 고르게 하면 남의 팀 사람을 고를 수 있고, 그건 서버가 거절하지만
    **고를 수 있는 것을 보여 주는 것 자체가 잘못된 안내**다.
    """

    def get(self, request, team_id):
        try:
            return Response(OpsTeamRepository.candidates(team_id))
        except psycopg.Error as exc:
            return to_response(exc)

    def post(self, request, team_id):
        serializer = TeamOwnerTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = OpsTeamRepository.transfer_owner(
                team_id=team_id,
                new_owner_account_id=serializer.validated_data["account_id"],
                actor_account_id=request.user.account_id,
                reason=serializer.validated_data["reason"],
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(result)
