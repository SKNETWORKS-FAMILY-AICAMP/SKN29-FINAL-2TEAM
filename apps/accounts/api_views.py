import logging
from secrets import compare_digest

import psycopg
from django.contrib.auth.hashers import check_password, make_password
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.db import AccountRepository, MemberInviteRepository
from backend.db.errors import (
    DuplicateRecord,
    PermissionDenied,
    RecordNotFound,
    ReferenceNotFound,
    RepositoryError,
)

from .authentication import BearerTokenAuthentication
from .emails import send_password_reset_mail
from .serializers import (
    InviteCodeSerializer,
    InviteCreateSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    SignupSerializer,
    account_response,
    invite_candidate_response,
    invite_preview_response,
    invite_response,
)
from .tokens import (
    InvalidToken,
    generate_invite_code,
    hash_invite_code,
    issue_password_reset_token,
    issue_token,
    password_fingerprint,
    read_password_reset_token,
)

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS_DETAIL = "이메일 또는 비밀번호가 올바르지 않습니다."
RESET_REQUEST_DETAIL = "가입된 이메일이라면 재설정 링크를 보냈습니다. 메일함을 확인해 주세요."
DEAD_RESET_LINK_DETAIL = "이미 사용됐거나 유효하지 않은 재설정 링크입니다. 다시 요청해 주세요."


def _repository_error_response(exc: Exception) -> Response:
    if isinstance(exc, RecordNotFound):
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, PermissionDenied):
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    if isinstance(exc, (DuplicateRecord, ReferenceNotFound)):
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


class SignupAPIView(APIView):
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        invite_code = data["invite_code"].strip()
        try:
            profile = AccountRepository.create(
                email=data["email"],
                password_hash=make_password(data["password"]),
                display_name=data["display_name"],
                invite_token_hash=hash_invite_code(invite_code) if invite_code else None,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        return Response(
            {"token": issue_token(profile["account_id"]), "account": account_response(profile)},
            status=status.HTTP_201_CREATED,
        )


class LoginAPIView(APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            account = AccountRepository.find_credentials(data["email"])
        except psycopg.Error as exc:
            return _repository_error_response(exc)

        # 존재하지 않는 이메일과 비밀번호 불일치를 구분해서 알려주지 않는다.
        if account is None or not check_password(data["password"], account["password_hash"]):
            return Response(
                {"detail": INVALID_CREDENTIALS_DETAIL},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if account["account_status"] != "ACTIVE":
            return Response(
                {"detail": "사용할 수 없는 계정입니다. 관리자에게 문의해 주세요."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            AccountRepository.touch_last_login(account["account_id"])
            profile = AccountRepository.get_profile(account["account_id"])
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        return Response(
            {"token": issue_token(profile["account_id"]), "account": account_response(profile)}
        )


class PasswordResetRequestAPIView(APIView):
    """재설정 링크를 메일로 보낸다.

    가입 여부에 따라 응답이 달라지면 계정 존재 여부가 노출되므로, 메일을
    보냈든 안 보냈든 항상 같은 응답을 준다. 발송 실패는 서버 로그로만 남긴다.
    """

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        try:
            account = AccountRepository.find_credentials(email)
        except psycopg.Error as exc:
            return _repository_error_response(exc)

        if account is not None and account["account_status"] == "ACTIVE":
            token = issue_password_reset_token(
                account_id=account["account_id"],
                password_hash=account["password_hash"],
            )
            try:
                send_password_reset_mail(
                    to_email=account["email"],
                    display_name=account["display_name"],
                    token=token,
                )
            except OSError:
                logger.exception("비밀번호 재설정 메일 발송 실패: %s", account["account_id"])

        return Response({"detail": RESET_REQUEST_DETAIL})


class PasswordResetConfirmAPIView(APIView):
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            payload = read_password_reset_token(data["token"])
        except InvalidToken as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            account = AccountRepository.find_credentials_by_id(payload.get("account_id", ""))
        except psycopg.Error as exc:
            return _repository_error_response(exc)

        # 지문이 어긋나면 발급 이후에 비밀번호가 이미 한 번 바뀐 것이다.
        if account is None or not compare_digest(
            payload.get("fingerprint", ""),
            password_fingerprint(account["password_hash"]),
        ):
            return Response(
                {"detail": DEAD_RESET_LINK_DETAIL},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if account["account_status"] != "ACTIVE":
            return Response(
                {"detail": "사용할 수 없는 계정입니다. 관리자에게 문의해 주세요."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            AccountRepository.update_password(
                account_id=account["account_id"],
                password_hash=make_password(data["password"]),
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        return Response({"detail": "비밀번호를 변경했습니다. 새 비밀번호로 로그인해 주세요."})


class CurrentAccountAPIView(AuthenticatedAPIView):
    def get(self, request):
        try:
            profile = AccountRepository.get_profile(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(account_response(profile))


class InvitePreviewAPIView(APIView):
    """가입 화면으로 넘어가기 전에 코드 유효성과 대상자를 확인한다.

    코드를 아는 사람만 조회할 수 있으므로 인증 없이 열어 둔다
    (`팀원_초대_계정_매핑_정책.md` 팀원 측 UX 흐름 1단계).
    """

    def post(self, request):
        serializer = InviteCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            row = MemberInviteRepository.preview(hash_invite_code(serializer.validated_data["code"]))
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(invite_preview_response(row))


class InviteCandidateListAPIView(AuthenticatedAPIView):
    def get(self, request):
        try:
            rows = MemberInviteRepository.list_candidates(request.user.account_id)
        except psycopg.Error as exc:
            return _repository_error_response(exc)
        return Response([invite_candidate_response(row) for row in rows])


class InviteListCreateAPIView(AuthenticatedAPIView):
    def get(self, request):
        try:
            rows = MemberInviteRepository.list_by_inviter(request.user.account_id)
        except psycopg.Error as exc:
            return _repository_error_response(exc)
        return Response([invite_response(row) for row in rows])

    def post(self, request):
        serializer = InviteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        code = generate_invite_code()
        try:
            row = MemberInviteRepository.create(
                invited_by=request.user.account_id,
                person_id=serializer.validated_data["person_id"],
                token_hash=hash_invite_code(code),
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        # 원문 코드는 저장하지 않으므로 이 응답에서만 확인할 수 있다.
        return Response(
            {**invite_response(row), "code": code},
            status=status.HTTP_201_CREATED,
        )


class InviteRevokeAPIView(AuthenticatedAPIView):
    def post(self, request, invite_id):
        try:
            MemberInviteRepository.revoke(
                invite_id=invite_id,
                account_id=request.user.account_id,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)
