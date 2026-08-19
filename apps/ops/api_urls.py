from django.urls import path

from .views.accounts import (
    AccountAdminView,
    AccountDetailView,
    AccountListView,
    AccountLockView,
    AccountUnlinkPersonView,
    AccountUnlockView,
)
from .views.audit import OperationLogView
from .views.connectors import ConnectorDetailView, ConnectorListView, ConnectorRevokeView
from .views.invites import (
    InviteDetailView,
    InviteDiscardView,
    InviteListView,
    InviteUnlinkView,
)
from .views.login import LoginView, LogoutView
from .views.mcp import McpDetailView, McpListCreateView, McpProbeView, McpTestView
from .views.models import (
    ModelDetailView,
    ModelListCreateView,
    ModelProbeView,
    TeamDefaultModelView,
)
from .views.teams import TeamContentView, TeamOwnerView, TeamsView
from .views.overview import OverviewView
from .views.purge import AccountPurgeView, TeamPurgeView
from .views.policies import InviteTtlView, NoticeDetailView, NoticeListCreateView, PolicyChangeListView

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="api_ops_auth_login"),
    path("auth/logout/", LogoutView.as_view(), name="api_ops_auth_logout"),
    path("overview/", OverviewView.as_view(), name="api_ops_overview"),
    path("teams/", TeamsView.as_view(), name="api_ops_teams"),
    path("teams/<str:team_id>/content/", TeamContentView.as_view(), name="api_ops_team_content"),
    path("teams/<str:team_id>/owner/", TeamOwnerView.as_view(), name="api_ops_team_owner"),
    path("teams/<str:team_id>/purge/", TeamPurgeView.as_view(), name="api_ops_team_purge"),
    path("accounts/", AccountListView.as_view(), name="api_ops_account_list"),
    path("accounts/<str:account_id>/", AccountDetailView.as_view(), name="api_ops_account_detail"),
    path("accounts/<str:account_id>/admin/", AccountAdminView.as_view(), name="api_ops_account_admin"),
    # 완전 삭제. 미리보기(GET)와 실행(DELETE)이 같은 주소다 — 자세한 이유는
    # `views/purge.py` 모듈 docstring.
    path("accounts/<str:account_id>/purge/", AccountPurgeView.as_view(), name="api_ops_account_purge"),
    path("accounts/<str:account_id>/lock/", AccountLockView.as_view(), name="api_ops_account_lock"),
    path("accounts/<str:account_id>/unlock/", AccountUnlockView.as_view(), name="api_ops_account_unlock"),
    path(
        "accounts/<str:account_id>/unlink-person/",
        AccountUnlinkPersonView.as_view(),
        name="api_ops_account_unlink_person",
    ),
    path("invites/", InviteListView.as_view(), name="api_ops_invite_list"),
    path("invites/<str:invite_id>/", InviteDetailView.as_view(), name="api_ops_invite_detail"),
    path("invites/<str:invite_id>/discard/", InviteDiscardView.as_view(), name="api_ops_invite_discard"),
    path("invites/<str:invite_id>/unlink/", InviteUnlinkView.as_view(), name="api_ops_invite_unlink"),
    path("connectors/", ConnectorListView.as_view(), name="api_ops_connector_list"),
    path("connectors/<str:conn_id>/", ConnectorDetailView.as_view(), name="api_ops_connector_detail"),
    path(
        "connectors/<str:conn_id>/revoke/",
        ConnectorRevokeView.as_view(),
        name="api_ops_connector_revoke",
    ),
    path("models/", ModelListCreateView.as_view(), name="api_ops_model_list"),
    path("models/probe/", ModelProbeView.as_view(), name="api_ops_model_probe"),
    # `models/<conn_id>/` 앞에 둔다 — 뒤에 있으면 이 경로가 모델 삭제로 잡힌다.
    path(
        "models/teams/<str:team_id>/default/",
        TeamDefaultModelView.as_view(),
        name="api_ops_team_default_model",
    ),
    path("models/<str:conn_id>/", ModelDetailView.as_view(), name="api_ops_model_detail"),
    path("mcp/", McpListCreateView.as_view(), name="api_ops_mcp_list"),
    # **`<server_id>` 앞에 둔다.** 뒤에 두면 `mcp/probe/` 가 서버 상세로 잡힌다
    # (모델 쪽에서 실제로 밟은 자리다 · `models/probe/`).
    path("mcp/probe/", McpProbeView.as_view(), name="api_ops_mcp_probe"),
    path("mcp/<str:server_id>/", McpDetailView.as_view(), name="api_ops_mcp_detail"),
    path("mcp/<str:server_id>/test/", McpTestView.as_view(), name="api_ops_mcp_test"),
    path("audit/operations/", OperationLogView.as_view(), name="api_ops_audit_operations"),
    path("policies/invite-ttl/", InviteTtlView.as_view(), name="api_ops_policies_invite_ttl"),
    path("policies/notices/", NoticeListCreateView.as_view(), name="api_ops_policies_notice_list"),
    path("policies/notices/<str:notice_id>/", NoticeDetailView.as_view(), name="api_ops_policies_notice_detail"),
    path("policies/changes/", PolicyChangeListView.as_view(), name="api_ops_policies_changes"),
]
