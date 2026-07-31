import psycopg
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import BearerTokenAuthentication
from backend.db import AccountRepository, TeamRepository
from backend.db.errors import RepositoryError
from backend.services import hr

from .serializers import organization_response, person_response, team_response


class TeamScopedAPIView(APIView):
    """팀 안에서만 보이는 조회의 공통 베이스.

    테넌트는 회사가 아니라 **팀**이다. 회사 전체가 우리 플랫폼을 쓰는 것이 아니라
    그 안의 그룹이 쓰기 때문이다. 팀이 아직 없는 계정(HR 확인만 하고 팀을 안 만든
    상태)은 빈 목록을 받는다 — 볼 수 있는 사람이 아직 없는 것이 맞다.
    """

    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def team_person_ids(self) -> list[str]:
        team_id = AccountRepository.team_id(self.request.user.account_id)
        return TeamRepository.member_person_ids(team_id)


def _unavailable(detail: str, exc: Exception) -> Response:
    return Response(
        {"detail": detail, "error": exc.__class__.__name__},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


class TeamAPIView(TeamScopedAPIView):
    """온보딩에서 팀장이 팀명을 붙여 팀을 만든다. 계정당 하나다."""

    def get(self, request):
        try:
            team = TeamRepository.get(AccountRepository.team_id(request.user.account_id))
        except psycopg.Error as exc:
            return _unavailable("팀 정보를 조회할 수 없습니다.", exc)

        if team is None:
            return Response({"detail": "아직 팀이 없습니다."}, status=status.HTTP_404_NOT_FOUND)
        return Response(team_response(team))

    def post(self, request):
        name = request.data.get("name") or ""
        person_ids = request.data.get("person_ids") or []
        if not isinstance(person_ids, list):
            return Response(
                {"detail": "person_ids는 배열이어야 합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            team = TeamRepository.create(
                owner_account_id=request.user.account_id,
                name=name,
                person_ids=[str(pid) for pid in person_ids],
            )
        except RepositoryError as exc:
            return _repository_error(exc)
        except psycopg.Error as exc:
            return _unavailable("팀을 만들 수 없습니다.", exc)

        return Response(team_response(team), status=status.HTTP_201_CREATED)


def _repository_error(exc: RepositoryError) -> Response:
    from backend.db.errors import DuplicateRecord, PermissionDenied, RecordNotFound

    if isinstance(exc, RecordNotFound):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, PermissionDenied):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, DuplicateRecord):
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_400_BAD_REQUEST
    return Response({"detail": str(exc)}, status=code)


class PersonListAPIView(TeamScopedAPIView):
    def get(self, request):
        try:
            rows = hr.list_persons(person_ids=self.team_person_ids())
        except psycopg.Error as exc:
            return _unavailable("직원 데이터를 조회할 수 없습니다.", exc)
        return Response([person_response(row) for row in rows])


class OrganizationListAPIView(TeamScopedAPIView):
    """팀원들이 실제로 속한 조직만 보여준다.

    조직도 전체가 아니다 — 팀이 쓰는 것은 자기 팀원의 소속 정보이지 회사
    조직도가 아니기 때문이다.
    """

    def get(self, request):
        try:
            persons = hr.list_persons(person_ids=self.team_person_ids())
            org_ids = sorted({p["org_id"] for p in persons if p["org_id"]})
            rows = hr.list_orgs(org_ids=org_ids)
        except psycopg.Error as exc:
            return _unavailable("조직 데이터를 조회할 수 없습니다.", exc)
        return Response([organization_response(row) for row in rows])
