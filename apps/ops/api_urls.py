from django.urls import path

from .views.accounts import AccountListView, AccountLockView, AccountUnlinkPersonView, AccountUnlockView
from .views.audit import (
    AssignmentRunLogView,
    DecisionLogView,
    OperationLogView,
    RecommendationLogView,
    ValidationLogView,
)
from .views.connectors import ConnectorListView
from .views.invites import InviteDiscardView, InviteListView, InviteUnlinkView
from .views.login import LoginView, LogoutView, MeView
from .views.organizations import OrganizationsView
from .views.overview import OverviewView
from .views.policies import InviteTtlView, NoticeDetailView, NoticeListCreateView, PolicyChangeListView

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="api_ops_auth_login"),
    path("auth/me/", MeView.as_view(), name="api_ops_auth_me"),
    path("auth/logout/", LogoutView.as_view(), name="api_ops_auth_logout"),
    path("overview/", OverviewView.as_view(), name="api_ops_overview"),
    path("organizations/", OrganizationsView.as_view(), name="api_ops_organizations"),
    path("accounts/", AccountListView.as_view(), name="api_ops_account_list"),
    path("accounts/<str:account_id>/lock/", AccountLockView.as_view(), name="api_ops_account_lock"),
    path("accounts/<str:account_id>/unlock/", AccountUnlockView.as_view(), name="api_ops_account_unlock"),
    path(
        "accounts/<str:account_id>/unlink-person/",
        AccountUnlinkPersonView.as_view(),
        name="api_ops_account_unlink_person",
    ),
    path("invites/", InviteListView.as_view(), name="api_ops_invite_list"),
    path("invites/<str:invite_id>/discard/", InviteDiscardView.as_view(), name="api_ops_invite_discard"),
    path("invites/<str:invite_id>/unlink/", InviteUnlinkView.as_view(), name="api_ops_invite_unlink"),
    path("connectors/", ConnectorListView.as_view(), name="api_ops_connector_list"),
    path("audit/operations/", OperationLogView.as_view(), name="api_ops_audit_operations"),
    path("audit/assignment-runs/", AssignmentRunLogView.as_view(), name="api_ops_audit_assignment_runs"),
    path("audit/recommendations/", RecommendationLogView.as_view(), name="api_ops_audit_recommendations"),
    path("audit/validations/", ValidationLogView.as_view(), name="api_ops_audit_validations"),
    path("audit/decisions/", DecisionLogView.as_view(), name="api_ops_audit_decisions"),
    path("policies/invite-ttl/", InviteTtlView.as_view(), name="api_ops_policies_invite_ttl"),
    path("policies/notices/", NoticeListCreateView.as_view(), name="api_ops_policies_notice_list"),
    path("policies/notices/<str:notice_id>/", NoticeDetailView.as_view(), name="api_ops_policies_notice_detail"),
    path("policies/changes/", PolicyChangeListView.as_view(), name="api_ops_policies_changes"),
]
