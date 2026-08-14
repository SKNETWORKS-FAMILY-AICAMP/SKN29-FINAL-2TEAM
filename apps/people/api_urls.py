from django.urls import path

from .api_views import (
    TeamAPIView,
    TeamMemberAPIView,
    TeamMemberDetailAPIView,
    TeamSettingAPIView,
)

urlpatterns = [
    path("teams/", TeamAPIView.as_view(), name="api_team"),
    path("teams/settings/", TeamSettingAPIView.as_view(), name="api_team_settings"),
    path("teams/members/", TeamMemberAPIView.as_view(), name="api_team_members"),
    path(
        "teams/members/<str:person_id>/",
        TeamMemberDetailAPIView.as_view(),
        name="api_team_member_detail",
    ),
]
