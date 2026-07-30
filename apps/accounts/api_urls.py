from django.urls import path

from .api_views import (
    CurrentAccountAPIView,
    InviteCandidateListAPIView,
    InviteListCreateAPIView,
    InvitePreviewAPIView,
    InviteRevokeAPIView,
    LoginAPIView,
    PasswordResetConfirmAPIView,
    PasswordResetRequestAPIView,
    SignupAPIView,
)

urlpatterns = [
    path("auth/signup/", SignupAPIView.as_view(), name="api_auth_signup"),
    path("auth/login/", LoginAPIView.as_view(), name="api_auth_login"),
    path("auth/me/", CurrentAccountAPIView.as_view(), name="api_auth_me"),
    path(
        "auth/password-reset/",
        PasswordResetRequestAPIView.as_view(),
        name="api_auth_password_reset",
    ),
    path(
        "auth/password-reset/confirm/",
        PasswordResetConfirmAPIView.as_view(),
        name="api_auth_password_reset_confirm",
    ),
    path("invites/", InviteListCreateAPIView.as_view(), name="api_invite_list_create"),
    path("invites/preview/", InvitePreviewAPIView.as_view(), name="api_invite_preview"),
    path("invites/candidates/", InviteCandidateListAPIView.as_view(), name="api_invite_candidates"),
    path("invites/<str:invite_id>/revoke/", InviteRevokeAPIView.as_view(), name="api_invite_revoke"),
]
