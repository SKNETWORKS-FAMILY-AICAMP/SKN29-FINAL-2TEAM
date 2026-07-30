from django.urls import path

from .api_views import (
    ConnectorListAPIView,
    GoogleDriveAuthorizeAPIView,
    GoogleDriveCallbackAPIView,
    JiraAuthorizeAPIView,
    JiraCallbackAPIView,
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
    path("connectors/jira/authorize/", JiraAuthorizeAPIView.as_view(), name="api_connector_jira_authorize"),
    path("connectors/jira/callback/", JiraCallbackAPIView.as_view(), name="api_connector_jira_callback"),
]
