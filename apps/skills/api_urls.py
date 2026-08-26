from django.urls import path

from .api_views import (
    MySkillShareAPIView,
    MySkillDetailAPIView,
    MySkillListCreateAPIView,
    TeamSkillDetailAPIView,
    TeamSkillImportAPIView,
    TeamSkillListCreateAPIView,
)

# 「내 파일」과 같은 이유로 계정 소유 자원은 `me/` 아래, 팀 소유 자원은
# `teams/` 아래 둔다 — 팀도 프로젝트도 아래에 걸지 않는다.
urlpatterns = [
    path("me/skills/", MySkillListCreateAPIView.as_view(), name="api_my_skills"),
    path("me/skills/<str:name>/", MySkillDetailAPIView.as_view(), name="api_my_skill_detail"),
    path("me/skills/<str:name>/share/", MySkillShareAPIView.as_view(), name="api_my_skill_share"),
    path("teams/skills/", TeamSkillListCreateAPIView.as_view(), name="api_team_skills"),
    path("teams/skills/<str:name>/", TeamSkillDetailAPIView.as_view(), name="api_team_skill_detail"),
    path(
        "teams/skills/<str:name>/import/",
        TeamSkillImportAPIView.as_view(),
        name="api_team_skill_import",
    ),
]
