from django.urls import path

from .api_views import (
    MySkillShareAPIView,
    MySkillDetailAPIView,
    MySkillListCreateAPIView,
    SkillRegistrationJobCancelAPIView,
    SkillRegistrationJobDetailAPIView,
    SkillRegistrationJobListCreateAPIView,
    SkillRegistrationJobRetryAPIView,
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
    # 검증 job — 정본 §14. "스킬 검증·등록 최종 설계.md".
    path(
        "skill-registration-jobs/",
        SkillRegistrationJobListCreateAPIView.as_view(),
        name="api_skill_registration_jobs",
    ),
    path(
        "skill-registration-jobs/<str:job_id>/",
        SkillRegistrationJobDetailAPIView.as_view(),
        name="api_skill_registration_job_detail",
    ),
    path(
        "skill-registration-jobs/<str:job_id>/cancel/",
        SkillRegistrationJobCancelAPIView.as_view(),
        name="api_skill_registration_job_cancel",
    ),
    path(
        "skill-registration-jobs/<str:job_id>/retry/",
        SkillRegistrationJobRetryAPIView.as_view(),
        name="api_skill_registration_job_retry",
    ),
]
