from django.urls import path

from .api_views import (
    ConnectorListAPIView,
    DriveChangeNotificationAPIView,
    GoogleDriveAuthorizeAPIView,
    GoogleDriveCallbackAPIView,
    GoogleDriveFileListAPIView,
    GoogleDriveFolderListAPIView,
    JiraAuthorizeAPIView,
    JiraCallbackAPIView,
    JiraProjectListAPIView,
    PeopleDbConnectAPIView,
    PeopleDbIdentityAPIView,
    PeopleDbSummaryAPIView,
)

urlpatterns = [
    path("connectors/", ConnectorListAPIView.as_view(), name="api_connector_list"),
    path(
        "connectors/people-db/",
        PeopleDbConnectAPIView.as_view(),
        name="api_connector_people_db_connect",
    ),
    path(
        "connectors/people-db/identity/",
        PeopleDbIdentityAPIView.as_view(),
        name="api_connector_people_db_identity",
    ),
    path(
        "connectors/people-db/summary/",
        PeopleDbSummaryAPIView.as_view(),
        name="api_connector_people_db_summary",
    ),
    path(
        "connectors/google-drive/authorize/",
        GoogleDriveAuthorizeAPIView.as_view(),
        name="api_connector_google_drive_authorize",
    ),
    path(
        "connectors/google-drive/callback/",
        GoogleDriveCallbackAPIView.as_view(),
        name="api_connector_google_drive_callback",
    ),
    path(
        "connectors/google-drive/folders/",
        GoogleDriveFolderListAPIView.as_view(),
        name="api_connector_google_drive_folders",
    ),
    path(
        "connectors/google-drive/files/",
        GoogleDriveFileListAPIView.as_view(),
        name="api_connector_google_drive_files",
    ),
    path("connectors/jira/authorize/", JiraAuthorizeAPIView.as_view(), name="api_connector_jira_authorize"),
    path("connectors/jira/callback/", JiraCallbackAPIView.as_view(), name="api_connector_jira_callback"),
    # Google 이 「뭔가 바뀌었다」고 두드리는 자리. **인증이 없다** — 저쪽이
    # 부르므로 세션이 없고, 채널을 열 때 심은 비밀값이 헤더로 되돌아오는 것이
    # 유일한 증명이다. `internal/` 아래 둔 것은 RunPod 다운로드 경로와 같은
    # 이유다: 사람이 쓰는 API 가 아니라 기계가 부르는 자리다.
    path(
        "internal/drive/notifications/",
        DriveChangeNotificationAPIView.as_view(),
        name="api_drive_notifications",
    ),
    path(
        "connectors/jira/projects/",
        JiraProjectListAPIView.as_view(),
        name="api_connector_jira_projects",
    ),
]
