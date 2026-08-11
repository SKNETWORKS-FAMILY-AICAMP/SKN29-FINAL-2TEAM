from django.urls import path

from .api_views import (
    McpServerDetailAPIView,
    McpServerListCreateAPIView,
    McpServerTestAPIView,
)

# MCP 서버는 **팀** 소유다(agent 와 같다). 프로젝트 아래가 아니라 팀 설정이다.
urlpatterns = [
    path("servers/", McpServerListCreateAPIView.as_view(), name="api_mcp_servers"),
    path("servers/<str:server_id>/", McpServerDetailAPIView.as_view(), name="api_mcp_server_detail"),
    path("servers/<str:server_id>/test/", McpServerTestAPIView.as_view(), name="api_mcp_server_test"),
]
