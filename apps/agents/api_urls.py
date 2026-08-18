from django.urls import path

from .api_views import (
    AgentActivateAPIView,
    AgentBuilderTestRunAPIView,
    AgentBuilderToolCheckAPIView,
    AgentDetailAPIView,
    AgentDisableAPIView,
    AgentListCreateAPIView,
    AgentToolCatalogAPIView,
    AgentVersionActivateAPIView,
    AgentVersionDetailAPIView,
    AgentVersionDisableAPIView,
    AgentVersionListCreateAPIView,
    CustomModelAPIView,
)

# 에이전트는 팀 소유다(MCP 서버와 같다). 프로젝트 아래가 아니다.
urlpatterns = [
    path("", AgentListCreateAPIView.as_view(), name="api_agents"),
    # 목록·build/*·모델은 모두 `<str:agent_id>` 보다 먼저 둔다 — 안 그러면
    # `agent_id` 가 'tools'·'build' 를 먹는다.
    path("tools/", AgentToolCatalogAPIView.as_view(), name="api_agent_tools"),
    path("custom-models/", CustomModelAPIView.as_view(), name="api_custom_models"),
    path("build/test/", AgentBuilderTestRunAPIView.as_view(), name="api_agent_builder_test"),
    path(
        "build/check-tools/",
        AgentBuilderToolCheckAPIView.as_view(),
        name="api_agent_builder_check_tools",
    ),
    # 새 버전 스키마(services/agent_runtime/ 전용) — 옛 `<str:agent_id>/`와
    # 겹치지 않게 `versions/` 아래 따로 둔다. 02 §17.1 작업자 A 몫.
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
    path("<str:agent_id>/", AgentDetailAPIView.as_view(), name="api_agent_detail"),
    path("<str:agent_id>/activate/", AgentActivateAPIView.as_view(), name="api_agent_activate"),
    path("<str:agent_id>/disable/", AgentDisableAPIView.as_view(), name="api_agent_disable"),
]
