import logging

import psycopg
from django.conf import settings
from django.http import HttpResponseRedirect
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

from .clients import (
    DRIVE_ROOT_ID,
    MAX_SCAN_DEPTH,
    get_drive_folders,
    list_drive_files,
    list_drive_folders,
    list_jira_projects,
)
from .serializers import connector_response, people_db_summary_response, person_response
from .oauth import (
    GOOGLE_DRIVE,
    GOOGLE_DRIVE_SCOPES,
    JIRA,
    JIRA_SCOPES,
    GoogleDriveOAuth,
    JiraOAuth,
    OAuthError,
    encrypt_credential,
    read_state,
)

LEADER_ONLY_DETAIL = "팀장만 외부 서비스를 연결할 수 있습니다."
logger = logging.getLogger(__name__)


def _safe_drive_id(value: str) -> bool:
    """Drive 검색식에 그대로 들어가는 값이라 따옴표·백슬래시를 막는다."""

    return "'" not in value and "\\" not in value


def _parse_depth(raw: str | None) -> int | None:
    """`proj_source.max_depth`와 같은 규약. `unlimited`·빈 값은 None이다."""

    if raw is None or raw == "":
        return 1
    if raw == "unlimited":
        return None
    depth = int(raw)  # ValueError는 호출자가 400으로 바꾼다.
    if depth < 1 or depth > MAX_SCAN_DEPTH:
        raise ValueError(f"탐색 깊이는 1~{MAX_SCAN_DEPTH} 사이여야 합니다.")
    return depth


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


def _google_drive_callback_redirect(result: str) -> HttpResponseRedirect:
    """Provider 입력을 URL에 되돌려 보내지 않는 고정 프론트 경로 리다이렉트."""

    path = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/onboarding/connectors"
    return HttpResponseRedirect(f"{path}?connector=google-drive&status={result}")


def _jira_callback_redirect(result: str) -> HttpResponseRedirect:
    path = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/onboarding/connectors"
    return HttpResponseRedirect(f"{path}?connector=jira&status={result}")


class GoogleDriveAuthorizeAPIView(AuthenticatedAPIView):
    """Bearer 인증을 받은 팀장만 Google 인가 URL을 발급받는다."""

    def get(self, request):
        try:
            profile = AccountRepository.get_profile(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        if account_role(profile) != "leader":
            return Response({"detail": LEADER_ONLY_DETAIL}, status=status.HTTP_403_FORBIDDEN)

        try:
            authorization_url = GoogleDriveOAuth.authorization_url(account_id=profile["account_id"])
        except OAuthError as exc:
            logger.warning("Google Drive authorization URL generation failed: %s", exc)
            return Response({"detail": "Google Drive 연결을 시작할 수 없습니다."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response({"authorization_url": authorization_url})


class GoogleDriveCallbackAPIView(APIView):
    """Google이 브라우저로 호출하는 OAuth 콜백. Bearer 인증을 사용하지 않는다."""

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        state = request.query_params.get("state", "")
        try:
            account_id = read_state(state=state, connector_type=GOOGLE_DRIVE)
            # 사용자가 Google 동의 화면에서 거부한 경우도 상태만 고정 URL로 전달한다.
            if request.query_params.get("error") or not request.query_params.get("code"):
                raise OAuthError("Google Drive authorization was denied or incomplete.")

            credential = GoogleDriveOAuth.exchange_code(code=request.query_params["code"])
            ConnectorRepository.connect_oauth(
                account_id=account_id,
                connector_type=GOOGLE_DRIVE,
                granted_scopes=GOOGLE_DRIVE_SCOPES,
                encrypted_credential=encrypt_credential(credential),
            )
        except (OAuthError, RepositoryError, psycopg.Error) as exc:
            # code, state, provider 오류 원문에는 인증 정보가 포함될 수 있어 URL·응답에 싣지 않는다.
            logger.warning("Google Drive OAuth callback failed: %s", exc)
            return _google_drive_callback_redirect("error")

        return _google_drive_callback_redirect("ok")


class JiraAuthorizeAPIView(AuthenticatedAPIView):
    """Bearer 인증을 받은 팀장만 Atlassian 인가 URL을 발급받는다."""

    def get(self, request):
        try:
            profile = AccountRepository.get_profile(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        if account_role(profile) != "leader":
            return Response({"detail": LEADER_ONLY_DETAIL}, status=status.HTTP_403_FORBIDDEN)

        try:
            authorization_url = JiraOAuth.authorization_url(account_id=profile["account_id"])
        except OAuthError as exc:
            logger.warning("Jira authorization URL generation failed: %s", exc)
            return Response({"detail": "Jira 연결을 시작할 수 없습니다."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response({"authorization_url": authorization_url})


class JiraCallbackAPIView(APIView):
    """Atlassian이 브라우저로 호출하는 OAuth 콜백. Bearer 인증을 사용하지 않는다."""

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        state = request.query_params.get("state", "")
        try:
            account_id = read_state(state=state, connector_type=JIRA)
            if request.query_params.get("error") or not request.query_params.get("code"):
                raise OAuthError("Jira authorization was denied or incomplete.")

            credential = JiraOAuth.exchange_code(code=request.query_params["code"])
            ConnectorRepository.connect_oauth(
                account_id=account_id,
                connector_type=JIRA,
                granted_scopes=JIRA_SCOPES,
                encrypted_credential=encrypt_credential(credential),
            )
        except (OAuthError, RepositoryError, psycopg.Error) as exc:
            logger.warning("Jira OAuth callback failed: %s", exc)
            return _jira_callback_redirect("error")

        return _jira_callback_redirect("ok")


class GoogleDriveFolderListAPIView(AuthenticatedAPIView):
    """Drive 폴더 조회. 선택 결과 저장은 `proj_source`(프로젝트 단위)의 일이다.

    `ids`를 주면 그 폴더들만, 없으면 `parent` 바로 아래를 돌려준다. 저장된 선택은
    폴더 id만 남기 때문에 이름을 되짚을 방법이 필요하다.
    """

    def get(self, request):
        raw_ids = request.query_params.get("ids")
        if raw_ids:
            folder_ids = [value for value in (part.strip() for part in raw_ids.split(",")) if value]
            try:
                folders = get_drive_folders(account_id=request.user.account_id, folder_ids=folder_ids)
            except OAuthError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
            except (RepositoryError, psycopg.Error) as exc:
                return _repository_error_response(exc)
            return Response(folders)

        parent_id = request.query_params.get("parent") or DRIVE_ROOT_ID
        if not _safe_drive_id(parent_id):
            return Response({"detail": "폴더 식별자가 올바르지 않습니다."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            folders = list_drive_folders(account_id=request.user.account_id, parent_id=parent_id)
        except OAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        return Response(folders)


class GoogleDriveFileListAPIView(AuthenticatedAPIView):
    """`parent` 폴더 아래의 파일. 어떤 문서가 들어올지 확인하는 용도다.

    `depth`는 선택한 폴더를 1단계로 센다. 생략하면 1(직속 파일만),
    `unlimited`면 제한 없음.
    """

    def get(self, request):
        parent_id = request.query_params.get("parent") or ""
        if not parent_id or not _safe_drive_id(parent_id):
            return Response({"detail": "폴더 식별자가 올바르지 않습니다."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            max_depth = _parse_depth(request.query_params.get("depth"))
        except ValueError:
            return Response({"detail": "탐색 깊이가 올바르지 않습니다."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            files = list_drive_files(
                account_id=request.user.account_id,
                parent_id=parent_id,
                max_depth=max_depth,
            )
        except OAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        return Response(files)


class JiraProjectListAPIView(AuthenticatedAPIView):
    """연결된 Jira 사이트의 프로젝트 목록. 조회만 한다."""

    def get(self, request):
        try:
            projects = list_jira_projects(account_id=request.user.account_id)
        except OAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        return Response(projects)
