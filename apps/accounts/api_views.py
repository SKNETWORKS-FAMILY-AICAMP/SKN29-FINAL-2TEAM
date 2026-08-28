import logging
from secrets import compare_digest

import psycopg
from django.contrib.auth.hashers import check_password, make_password
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.http import HttpResponse

from backend.db import AccountRepository, MemberInviteRepository, log_audit
from backend.services import storage
from backend.services.storage import STORAGE_ERRORS
from backend.services.hr import list_person_skills
from backend.db.errors import (
    DuplicateRecord,
    PermissionDenied,
    RecordNotFound,
    ReferenceNotFound,
    RepositoryError,
)

from .authentication import BearerTokenAuthentication
from .emails import send_password_reset_mail
from .permissions import require_leader
from .serializers import (
    InviteCodeSerializer,
    InviteCreateSerializer,
    LoginSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    SignupSerializer,
    account_response,
    auth_result_response,
    invite_candidate_response,
    invite_preview_response,
    invite_response,
    skill_response,
)
from .tokens import (
    InvalidToken,
    generate_invite_code,
    hash_invite_code,
    issue_password_reset_token,
    password_fingerprint,
    read_password_reset_token,
)

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS_DETAIL = "이메일 또는 비밀번호가 올바르지 않습니다."
RESET_REQUEST_DETAIL = "가입된 이메일이라면 재설정 링크를 보냈습니다. 메일함을 확인해 주세요."
DEAD_RESET_LINK_DETAIL = "이미 사용됐거나 유효하지 않은 재설정 링크입니다. 다시 요청해 주세요."


def _log_audit_safely(**kwargs) -> None:
    """감사 로그는 부수 기록이다. 여기서 실패해도 이미 끝난 본 작업(가입/로그인/
    비밀번호 재설정)까지 오류로 되돌리면 안 된다 — 특히 가입은 계정이 만들어진
    뒤라, 503으로 응답하면 재시도 시 '이미 존재하는 이메일'로 막힌다."""

    try:
        log_audit(**kwargs)
    except psycopg.Error:
        logger.warning("감사 로그 기록 실패: action=%s", kwargs.get("action"))


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
            _log_audit_safely(actor_account_id=profile["account_id"], action="SIGNUP")
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        return Response(auth_result_response(profile), status=status.HTTP_201_CREATED)


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
            _log_audit_safely(actor_account_id=account["account_id"], action="LOGIN")
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        return Response(auth_result_response(profile))


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
            _log_audit_safely(actor_account_id=account["account_id"], action="PASSWORD_RESET")
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        return Response({"detail": "비밀번호를 변경했습니다. 새 비밀번호로 로그인해 주세요."})


class PasswordChangeAPIView(AuthenticatedAPIView):
    """로그인한 사용자가 스스로 비밀번호를 바꾼다.

    현재 비밀번호를 확인한다 — 토큰만으로 바꾸게 하면 자리를 비운 사이 남이
    세션을 잡아 비밀번호를 갈아 끼울 수 있다.

    **틀렸을 때 이메일 존재 여부는 흘리지 않는다.** 이미 로그인한 사람이라
    계정이 있다는 것은 서로 아는 사실이고, 여기서 감출 것은 비밀번호뿐이다.
    """

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        account_id = request.user.account_id

        try:
            account = AccountRepository.find_credentials_by_id(account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        if account is None:
            return Response(
                {"detail": "존재하지 않는 계정입니다."}, status=status.HTTP_404_NOT_FOUND
            )
        if not check_password(data["current_password"], account["password_hash"]):
            return Response(
                {"detail": "현재 비밀번호가 일치하지 않습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            AccountRepository.update_password(
                account_id=account_id,
                password_hash=make_password(data["password"]),
            )
            _log_audit_safely(actor_account_id=account_id, action="PASSWORD_CHANGE")
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        # 토큰을 무효화하지 않는다. 서버가 발급 목록을 들고 있지 않아 지금은
        # 그럴 수 없고, 있는 것처럼 안내하면 거짓이 된다.
        return Response({"detail": "비밀번호를 변경했습니다."})


# 프로필 사진 상한. 아바타는 화면에서 52px로 그려지므로 이보다 클 이유가 없다.
# 상한이 없으면 한 번의 요청으로 디스크를 채울 수 있다.
_AVATAR_MAX_BYTES = 2 * 1024 * 1024


class CurrentAvatarAPIView(AuthenticatedAPIView):
    """내 프로필 사진. 올리고, 보고, 지운다.

    남의 사진 경로는 열지 않는다 — 지금 필요한 것은 본인 것뿐이고, 팀원 사진이
    필요해지면 팀 범위를 확인하는 경로를 따로 만드는 편이 안전하다.
    """

    def get(self, request):
        try:
            key = AccountRepository.avatar_key(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        if not key or not storage.exists(key):
            # 아직 안 올렸다. 화면은 이름 첫 글자로 대신하므로 404가 정상 흐름이다.
            return Response({"detail": "등록된 프로필 사진이 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        data = storage.load(key)
        mime = storage.sniff_image_type(data) or "application/octet-stream"
        response = HttpResponse(data, content_type=mime)
        # 같은 URL로 새 사진이 올라오므로 캐시하면 옛 사진이 남는다.
        response["Cache-Control"] = "no-store"
        return response

    def put(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "파일을 첨부해 주세요."}, status=status.HTTP_400_BAD_REQUEST)
        if upload.size > _AVATAR_MAX_BYTES:
            return Response(
                {"detail": "프로필 사진은 2MB 이하여야 합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = upload.read()
        # Content-Type 은 보내는 쪽이 정하는 값이라 믿지 않는다. 실제 바이트로 본다.
        mime = storage.sniff_image_type(data)
        if mime is None:
            return Response(
                {"detail": "JPG, PNG, WEBP 이미지만 올릴 수 있습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        account_id = request.user.account_id
        key = storage.build_avatar_key(account_id=account_id, mime_type=mime)
        try:
            # 파일을 먼저 쓰고 기록을 나중에 한다. 반대 순서면 "DB에는 있다는데
            # 파일이 없는" 상태가 생겨 화면이 깨진 이미지를 그린다.
            storage.save(key, data)
            AccountRepository.set_avatar_key(account_id=account_id, avatar_key=key)
        except STORAGE_ERRORS as exc:
            return Response(
                {"detail": f"사진을 저장하지 못했습니다: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        return Response({"detail": "프로필 사진을 변경했습니다."})

    def delete(self, request):
        """기록만 지운다. 파일은 같은 키로 덮어써지므로 남겨 둬도 새 사진을 막지 않는다."""

        try:
            AccountRepository.set_avatar_key(account_id=request.user.account_id, avatar_key=None)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response({"detail": "프로필 사진을 삭제했습니다."})


class CurrentAccountAPIView(AuthenticatedAPIView):
    """설정의 「내 프로필」이 쓰는 단건 조회.

    스킬을 같이 준다 — 사람의 신원(HR)과 스킬은 같은 화면에서 함께 읽히고,
    나눠 부르면 왕복만 늘어난다.
    """

    def get(self, request):
        try:
            profile = AccountRepository.get_profile(request.user.account_id)
            person = profile.get("person")
            skills = list_person_skills(person["person_id"] if person else None)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(account_response(profile) | {"skills": [skill_response(s) for s in skills]})


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


#: 초대는 팀을 늘리는 일이라 팀장의 것이다. 발급과 폐기가 같은 문구를 쓴다.
INVITE_LEADER_ONLY = "팀장만 팀원을 초대할 수 있습니다."


class InviteListCreateAPIView(AuthenticatedAPIView):
    def get(self, request):
        try:
            rows = MemberInviteRepository.list_by_inviter(request.user.account_id)
        except psycopg.Error as exc:
            return _repository_error_response(exc)
        return Response([invite_response(row) for row in rows])

    def post(self, request):
        # 화면은 팀원에게 초대 버튼을 안 보여 주지만, 그건 문지기가 아니다.
        if denied := require_leader(request.user.account_id, INVITE_LEADER_ONLY):
            return denied

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
        if denied := require_leader(request.user.account_id, INVITE_LEADER_ONLY):
            return denied

        try:
            MemberInviteRepository.revoke(
                invite_id=invite_id,
                account_id=request.user.account_id,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)
