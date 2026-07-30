import psycopg
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import BearerTokenAuthentication
from apps.accounts.serializers import account_role
from backend.db import AccountRepository, ConnectorRepository
from backend.db.errors import (
    PermissionDenied,
    RecordNotFound,
    ReferenceNotFound,
    RepositoryError,
)

from .serializers import connector_response, people_db_summary_response, person_response

LEADER_ONLY_DETAIL = "팀장만 외부 서비스를 연결할 수 있습니다."


def _repository_error_response(exc: Exception) -> Response:
    if isinstance(exc, RecordNotFound):
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, PermissionDenied):
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    if isinstance(exc, ReferenceNotFound):
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    if isinstance(exc, RepositoryError):
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(
        {"detail": "데이터베이스 요청을 처리할 수 없습니다.", "error": exc.__class__.__name__},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


class AuthenticatedAPIView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]


class ConnectorListAPIView(AuthenticatedAPIView):
    def get(self, request):
        try:
            rows = ConnectorRepository.list_for_account(request.user.account_id)
        except psycopg.Error as exc:
            return _repository_error_response(exc)
        return Response([connector_response(row) for row in rows])


class PeopleDbIdentityAPIView(AuthenticatedAPIView):
    """HR에서 찾은 본인 후보. 사용자가 확인하기 전이라 매핑은 만들지 않는다."""

    def get(self, request):
        try:
            profile = AccountRepository.get_profile(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        if account_role(profile) != "leader":
            return Response({"detail": LEADER_ONLY_DETAIL}, status=status.HTTP_403_FORBIDDEN)

        try:
            person = ConnectorRepository.find_identity(
                account_id=profile["account_id"],
                email=profile["email"],
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        return Response(person_response(person))


class PeopleDbConnectAPIView(AuthenticatedAPIView):
    """HR(People DB) 연결. 온보딩의 첫 단계이자 다른 커넥터의 전제 조건."""

    def post(self, request):
        try:
            profile = AccountRepository.get_profile(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        if account_role(profile) != "leader":
            return Response({"detail": LEADER_ONLY_DETAIL}, status=status.HTTP_403_FORBIDDEN)

        try:
            summary = ConnectorRepository.connect_people_db(
                account_id=profile["account_id"],
                email=profile["email"],
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        return Response(people_db_summary_response(summary), status=status.HTTP_201_CREATED)


class PeopleDbSummaryAPIView(AuthenticatedAPIView):
    """이미 연결된 계정의 HR 요약. 연결 전에는 HR 데이터를 보여주지 않는다."""

    def get(self, request):
        account_id = request.user.account_id
        try:
            connected = any(
                row["connector_type"] == ConnectorRepository.PEOPLE_DB
                and row["auth_status"] == "CONNECTED"
                for row in ConnectorRepository.list_for_account(account_id)
            )
            if not connected:
                return Response(
                    {"detail": "People DB가 연결되지 않았습니다."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            summary = ConnectorRepository.people_db_summary(account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        return Response(people_db_summary_response(summary))
