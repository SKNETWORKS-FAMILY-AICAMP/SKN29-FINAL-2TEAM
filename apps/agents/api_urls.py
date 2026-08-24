from django.urls import path

from .api_views import (
    AgentToolCatalogAPIView,
    AgentVersionActivateAPIView,
    AgentVersionDependentsAPIView,
    AgentVersionDetailAPIView,
    AgentVersionDisableAPIView,
    AgentVersionFavoriteAPIView,
    AgentVersionListCreateAPIView,
    CustomModelAPIView,
)

# 에이전트는 팀 소유다(MCP 서버와 같다). 프로젝트 아래가 아니다.
#
# 2026-08-22에 레거시 비버전 스키마(`agent`/`agent_tool`)의 CRUD·활성화·빌더
# 테스트 라우트를 전부 지웠다. 그래서 `<str:agent_id>/` 를 먹는 라우트가 더는
# 없고, 옛 주석이 걱정하던 "`agent_id` 가 'tools'·'build' 를 먹는다" 문제도
# 같이 사라졌다 — 순서 의존이 없어졌지만 읽는 순서는 그대로 둔다.
urlpatterns = [
    path("tools/", AgentToolCatalogAPIView.as_view(), name="api_agent_tools"),
    path("custom-models/", CustomModelAPIView.as_view(), name="api_custom_models"),
    # 에이전트 정의는 전부 `versions/` 아래 하나뿐이다.
    path("versions/", AgentVersionListCreateAPIView.as_view(), name="api_agent_versions"),
    path(
        "versions/<str:agent_id>/",
        AgentVersionDetailAPIView.as_view(),
        name="api_agent_version_detail",
    ),
    path(
        "versions/<str:agent_id>/activate/",
        AgentVersionActivateAPIView.as_view(),
        name="api_agent_version_activate",
    ),
    path(
        "versions/<str:agent_id>/disable/",
        AgentVersionDisableAPIView.as_view(),
        name="api_agent_version_disable",
    ),
    path(
        "versions/<str:agent_id>/dependents/",
        AgentVersionDependentsAPIView.as_view(),
        name="api_agent_version_dependents",
    ),
    path(
        "versions/<str:agent_id>/favorite/",
        AgentVersionFavoriteAPIView.as_view(),
        name="api_agent_version_favorite",
    ),
]
