"""운영자 로그인·세션 확인·로그아웃 API."""

import logging

import psycopg
from django.contrib.auth.hashers import check_password
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.api_errors import to_response
from backend.db import AccountRepository, log_audit

from ..authentication import AdminView
from ..serializers import LoginSerializer, admin_response
from ..tokens import issue_token

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS_DETAIL = "이메일 또는 비밀번호가 올바르지 않습니다."
INACTIVE_ACCOUNT_DETAIL = "사용할 수 없는 계정입니다. 운영자에게 문의해 주세요."
NOT_ADMIN_DETAIL = "운영자 권한이 없는 계정입니다."


class LoginView(APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            account = AccountRepository.find_credentials(data["email"])
        except psycopg.Error as exc:
            return to_response(exc)

        # 존재하지 않는 이메일과 비밀번호 불일치를 구분해서 알려주지 않는다.
        if account is None or not check_password(data["password"], account["password_hash"]):
            return Response({"detail": INVALID_CREDENTIALS_DETAIL}, status=status.HTTP_401_UNAUTHORIZED)
        if account["account_status"] != "ACTIVE":
            return Response({"detail": INACTIVE_ACCOUNT_DETAIL}, status=status.HTTP_403_FORBIDDEN)
        if not account["is_admin"]:
            return Response({"detail": NOT_ADMIN_DETAIL}, status=status.HTTP_403_FORBIDDEN)

        try:
            AccountRepository.touch_last_login(account["account_id"])
            log_audit(actor_account_id=account["account_id"], action="OPS_LOGIN")
        except psycopg.Error as exc:
            return to_response(exc)

        return Response({"token": issue_token(account["account_id"]), "admin": admin_response(account)})


class MeView(AdminView):
    def get(self, request):
        admin = request.user
        return Response(
            admin_response(
                {
                    "account_id": admin.account_id,
                    "email": admin.email,
                    "display_name": admin.display_name,
                }
            )
        )


class LogoutView(AdminView):
    """서버에 세션을 두지 않으므로(`accounts/tokens.py`와 동일한 설계) 실제 토큰
    무효화는 못 하고, 로그아웃 사실만 감사 로그에 남긴다."""

    def post(self, request):
        try:
            log_audit(actor_account_id=request.user.account_id, action="OPS_LOGOUT")
        except psycopg.Error as exc:
            return to_response(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)
