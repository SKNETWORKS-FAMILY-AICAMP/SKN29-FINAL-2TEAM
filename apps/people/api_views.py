import psycopg
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import BearerTokenAuthentication
from apps.accounts.permissions import require_leader
from backend.db import AccountRepository, TeamRepository
from backend.db.errors import RepositoryError
from backend.services import hr

from .serializers import (
    team_member_response,
    team_response,
    team_setting_response,
)


class TeamScopedAPIView(APIView):
    """팀 안에서만 보이는 조회의 공통 베이스.

    테넌트는 회사가 아니라 **팀**이다. 회사 전체가 우리 플랫폼을 쓰는 것이 아니라
    그 안의 그룹이 쓰기 때문이다. 팀이 아직 없는 계정(HR 확인만 하고 팀을 안 만든
    상태)은 빈 목록을 받는다 — 볼 수 있는 사람이 아직 없는 것이 맞다.
    """

    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]


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


class TeamMemberAPIView(TeamScopedAPIView):
    """팀 명부. 사람·계정·초대를 한 줄로 본다.

    초대 현황과 다르다 — 초대는 "계정을 만들라고 보낸 것"이고 명부는 "업무 배정
    대상"이다. 직접 가입한 팀장은 초대 기록이 없어 초대 목록에는 아예 없다.
    """

    def get(self, request):
        try:
            rows = TeamRepository.list_members(request.user.account_id)
        except psycopg.Error as exc:
            return _unavailable("팀원 목록을 조회할 수 없습니다.", exc)
        return Response([team_member_response(row) for row in rows])

    def post(self, request):
        if denied := require_leader(request.user.account_id, TEAM_LEADER_ONLY):
            return denied

        person_id = str(request.data.get("person_id") or "").strip()
        if not person_id:
            return Response(
                {"detail": "person_id를 보내 주세요."}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            TeamRepository.add_member_for(
                account_id=request.user.account_id,
                person_id=person_id,
            )
            rows = TeamRepository.list_members(request.user.account_id)
        except RepositoryError as exc:
            return _repository_error(exc)
        except psycopg.Error as exc:
            return _unavailable("팀원을 추가할 수 없습니다.", exc)
        return Response([team_member_response(row) for row in rows])


class TeamMemberDetailAPIView(TeamScopedAPIView):
    def delete(self, request, person_id):
        if denied := require_leader(request.user.account_id, TEAM_LEADER_ONLY):
            return denied

        try:
            TeamRepository.remove_member(
                account_id=request.user.account_id,
                person_id=person_id,
            )
            rows = TeamRepository.list_members(request.user.account_id)
        except RepositoryError as exc:
            return _repository_error(exc)
        except psycopg.Error as exc:
            return _unavailable("팀원을 뺄 수 없습니다.", exc)
        return Response([team_member_response(row) for row in rows])


def _optional_number(raw: object, *, name: str, low: float, high: float, integer: bool):
    """비우면 "설정 안 함"(None)이다. 0을 넣으면 용량이 0이 되므로 하한을 둔다."""

    if raw is None or raw == "":
        return None
    try:
        value = int(raw) if integer else float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}은(는) 숫자여야 합니다.") from exc
    if not low <= value <= high:
        raise ValueError(f"{name}은(는) {low:g}~{high:g} 사이여야 합니다.")
    return value


class TeamSettingAPIView(TeamScopedAPIView):
    """팀 업무량 기준.

    셋 다 비울 수 있고 비우면 "설정 안 함"이다 — HR 값·100%·4주로 돌아간다.
    HR 값을 우리 테이블에 복사해 두지 않는 이유는, 복사하면 HR이 바뀌었을 때
    사본이 조용히 낡고 화면이 낡은 값을 "현재 기준"이라고 말하게 되기 때문이다.
    """

    def get(self, request):
        try:
            return Response(team_setting_response(TeamRepository.settings(request.user.account_id)))
        except RepositoryError as exc:
            return _repository_error(exc)
        except psycopg.Error as exc:
            return _unavailable("팀 설정을 조회할 수 없습니다.", exc)

    def put(self, request):
        if denied := require_leader(request.user.account_id, TEAM_LEADER_ONLY):
            return denied

        try:
            # 주 168시간이 물리적 상한이다. 그 위는 입력 실수다.
            capacity = _optional_number(
                request.data.get("capacity_wk_hours"), name="주 근무시간", low=1, high=168, integer=False
            )
            # 100 미만이면 정상 부하를 과부하로 표시하게 된다.
            overload = _optional_number(
                request.data.get("overload_pct"), name="과부하 기준", low=100, high=300, integer=True
            )
            # 1주 미만은 기간이 아니고, 반년을 넘으면 "지금 부하"가 아니다.
            weeks = _optional_number(
                request.data.get("workload_weeks"), name="조회 기간", low=1, high=26, integer=True
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            settings = TeamRepository.update_settings(
                account_id=request.user.account_id,
                capacity_wk_hours=capacity,
                overload_pct=overload,
                workload_weeks=weeks,
            )
        except RepositoryError as exc:
            return _repository_error(exc)
        except psycopg.Error as exc:
            return _unavailable("팀 설정을 저장할 수 없습니다.", exc)
        return Response(team_setting_response(settings))
