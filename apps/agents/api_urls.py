from django.urls import path

from .api_views import (
    AgentDetailAPIView,
    AgentListCreateAPIView,
    AgentToolCatalogAPIView,
    MainModelAPIView,
    CustomModelAPIView,
    CustomModelProbeAPIView,
)

# 에이전트는 팀 소유다(MCP 서버와 같다). 프로젝트 아래가 아니다.
urlpatterns = [
    path("", AgentListCreateAPIView.as_view(), name="api_agents"),
    # 목록보다 먼저 둔다 — `<str:agent_id>` 가 'tools' 를 먹지 않게.
    path("tools/", AgentToolCatalogAPIView.as_view(), name="api_agent_tools"),
    path("main-model/", MainModelAPIView.as_view(), name="api_agent_main_model"),
    path("custom-models/", CustomModelAPIView.as_view(), name="api_custom_models"),
    path("custom-models/probe/", CustomModelProbeAPIView.as_view(), name="api_custom_models_probe"),
    path("<str:agent_id>/", AgentDetailAPIView.as_view(), name="api_agent_detail"),
]
