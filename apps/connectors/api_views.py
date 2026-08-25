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
from backend.db import (
    AccountRepository,
    ConnectorRepository,
    ProjectSourceRepository,
    TeamRepository,
    log_audit,
)
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


def _log_audit_safely(**kwargs) -> None:
    """감사 로그는 부수 기록이다. 특히 OAuth 콜백에서 실패하면 실제 연결은
    끝났는데도 사용자에게 '연결 실패' 리다이렉트를 보내게 되므로, 여기서
    실패해도 본 작업(연결) 결과에 영향을 주면 안 된다."""

    try:
        log_audit(**kwargs)
    except psycopg.Error:
        logger.warning("감사 로그 기록 실패: action=%s", kwargs.get("action"))


def _collect_jira_projects_safely(account_id: str) -> None:
    """연결된 Jira 사이트의 프로젝트를 **전부** 우리 프로젝트로 등록한다.

    사람이 고르는 단계를 없앴다(8/12 PM 결정). 무엇을 읽을지 미리 고르게 하면
    연결 직후 화면이 비어 있고, 고르지 않은 프로젝트의 업무는 부하 계산에서
    조용히 빠진다 — 빠진 줄 모르는 숫자가 맞는 숫자처럼 보인다.

    `register_from_jira`는 목록에 **없는** 키의 소스를 지운다. 여기서는 접근
    가능한 전체를 넘기므로 지워지는 것이 없다. 이미 등록된 키는 이름만 갱신되고
    프로젝트가 새로 생기지 않는다(중복 방지는 그쪽에 있다).

    감사 로그와 같은 이유로 실패해도 삼킨다 — 수집이 안 됐다고 방금 끝난 연결을
    '실패'로 되돌리면, 자격증명은 저장돼 있는데 화면은 미연결로 보인다.

    **다만 여기서 실패하면 되살릴 길은 재연결뿐이다.** 목록의 「갱신」은 이미
    등록된 소스의 이슈를 다시 읽는 것이라(`/team/tasks/sync/`), 등록 자체가 없는
    프로젝트에는 읽을 것이 없다 — 「갱신이 다시 시도한다」고 적어 두었던 것을
    바로잡는다(2026-08-13). 사람이 고르는 화면은 없앴으므로 수동 등록 경로도
    화면에는 없다.
    """

    try:
        projects = list_jira_projects(account_id=account_id)
        if not projects:
            return
        ProjectSourceRepository.register_from_jira(
            account_id=account_id,
            selections=[
                {"project_key": project["project_key"], "name": project["name"]}
                for project in projects
            ],
        )
    except (OAuthError, RepositoryError, psycopg.Error) as exc:
        logger.warning("Jira 프로젝트 전체 수집 실패: account=%s (%s)", account_id, exc)


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
    """지금 무엇이 연결돼 있는가. **팀의 상태이지 내 상태가 아니다.**

    `connector_conn` 은 연결한 계정에만 행이 생기고 연결은 팀장만 할 수 있어서,
    누른 사람의 `account_id` 로 그대로 읽으면 **팀원에게는 늘 빈 목록**이 온다 —
    설정 > 커넥터가 세 자리를 전부 「미연결」로 그렸다. 팀장이 연결한 데이터를
    그대로 쓰는 팀원이 정작 그것이 붙어 있는지 볼 수 없었다.

    자격증명을 쓰는 쪽은 이미 같은 고침이 있다(`apps/projects/api_views.py` 의
    `_jira_credential_account_id`, `services/harness/registry.py` 의 같은 이름
    함수 — 2026-08-19). **읽기만 하는 이 조회에 그 처리가 빠져 있었다.**

    팀장 자신은 `leader_account_id` 가 곧 자기 계정이라 전과 같다. 팀이 없으면
    (가입 직후 등) 원래대로 자기 계정을 읽는다.
    """

    def get(self, request):
        try:
            team_id = AccountRepository.team_id(request.user.account_id)
            owner = (TeamRepository.leader_account_id(team_id) if team_id else None) or request.user.account_id
            rows = ConnectorRepository.list_for_account(owner)
        except (RepositoryError, psycopg.Error) as exc:
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
            _log_audit_safely(
                actor_account_id=profile["account_id"],
                action="CONNECTOR_CONNECT",
                target_type="CONNECTOR",
                payload={"connector_type": ConnectorRepository.PEOPLE_DB},
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


#: 연결이 끝난 사람이 돌아오는 자리. 온보딩 화면을 없애면서 Settings 로 옮겼다
#: (5차 단계 4) — 연결·폴더 설정·상태가 전부 그 탭에 있다.
CONNECTOR_RETURN_PATH = "/settings/connectors"


def _google_drive_callback_redirect(result: str) -> HttpResponseRedirect:
    """Provider 입력을 URL에 되돌려 보내지 않는 고정 프론트 경로 리다이렉트."""

    path = f"{settings.FRONTEND_BASE_URL.rstrip('/')}{CONNECTOR_RETURN_PATH}"
    return HttpResponseRedirect(f"{path}?connector=google-drive&status={result}")


def _jira_callback_redirect(result: str) -> HttpResponseRedirect:
    path = f"{settings.FRONTEND_BASE_URL.rstrip('/')}{CONNECTOR_RETURN_PATH}"
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
            _log_audit_safely(
                actor_account_id=account_id,
                action="CONNECTOR_CONNECT",
                target_type="CONNECTOR",
                payload={"connector_type": GOOGLE_DRIVE},
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
            _log_audit_safely(
                actor_account_id=account_id,
                action="CONNECTOR_CONNECT",
                target_type="CONNECTOR",
                payload={"connector_type": JIRA},
            )
        except (OAuthError, RepositoryError, psycopg.Error) as exc:
            logger.warning("Jira OAuth callback failed: %s", exc)
            return _jira_callback_redirect("error")

        # 연결이 끝난 뒤다. 여기서 실패해도 연결은 연결이다.
        _collect_jira_projects_safely(account_id)

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
