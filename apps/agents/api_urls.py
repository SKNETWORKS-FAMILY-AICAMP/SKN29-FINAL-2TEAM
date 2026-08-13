from django.urls import path

from .api_views import (
    AgentActivateAPIView,
    AgentBuilderCheckAPIView,
    AgentBuilderInstructionRecheckAPIView,
    AgentBuilderTestRunAPIView,
    AgentBuilderToolCheckAPIView,
    AgentDetailAPIView,
    AgentDisableAPIView,
    AgentListCreateAPIView,
    AgentToolCatalogAPIView,
    CustomModelAPIView,
    MainModelAPIView,
)

# 에이전트는 팀 소유다(MCP 서버와 같다). 프로젝트 아래가 아니다.
urlpatterns = [
    path("", AgentListCreateAPIView.as_view(), name="api_agents"),
    # 목록·build/*·모델은 모두 `<str:agent_id>` 보다 먼저 둔다 — 안 그러면
    # `agent_id` 가 'tools'·'build'·'main-model' 을 먹는다.
    path("tools/", AgentToolCatalogAPIView.as_view(), name="api_agent_tools"),
    path("main-model/", MainModelAPIView.as_view(), name="api_agent_main_model"),
    path("custom-models/", CustomModelAPIView.as_view(), name="api_custom_models"),
    path("build/check/", AgentBuilderCheckAPIView.as_view(), name="api_agent_builder_check"),
    path(
        "build/recheck-instruction/",
        AgentBuilderInstructionRecheckAPIView.as_view(),
        name="api_agent_builder_recheck_instruction",
    ),
    path("build/test/", AgentBuilderTestRunAPIView.as_view(), name="api_agent_builder_test"),
    path(
        "build/check-tools/",
        AgentBuilderToolCheckAPIView.as_view(),
        name="api_agent_builder_check_tools",
    ),
    path("<str:agent_id>/", AgentDetailAPIView.as_view(), name="api_agent_detail"),
    path("<str:agent_id>/activate/", AgentActivateAPIView.as_view(), name="api_agent_activate"),
    path("<str:agent_id>/disable/", AgentDisableAPIView.as_view(), name="api_agent_disable"),
]
