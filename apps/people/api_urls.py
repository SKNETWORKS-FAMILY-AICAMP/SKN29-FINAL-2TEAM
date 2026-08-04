from django.urls import path

from .api_views import (
    OrganizationListAPIView,
    PersonListAPIView,
    TeamAPIView,
    TeamMemberAPIView,
    TeamMemberDetailAPIView,
)

urlpatterns = [
    path("organizations/", OrganizationListAPIView.as_view(), name="api_organization_list"),
    path("people/", PersonListAPIView.as_view(), name="api_person_list"),
    path("teams/", TeamAPIView.as_view(), name="api_team"),
    path("teams/members/", TeamMemberAPIView.as_view(), name="api_team_members"),
    path(
        "teams/members/<str:person_id>/",
        TeamMemberDetailAPIView.as_view(),
        name="api_team_member_detail",
    ),
]
