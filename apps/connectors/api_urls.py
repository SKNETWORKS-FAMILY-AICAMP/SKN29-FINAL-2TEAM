from django.urls import path

from .api_views import (
    ConnectorListAPIView,
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
]
