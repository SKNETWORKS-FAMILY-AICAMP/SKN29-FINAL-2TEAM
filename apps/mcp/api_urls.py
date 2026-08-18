from django.urls import path

from .api_views import McpServerListAPIView

# 커스텀 도구 은 **팀** 소유다(agent 와 같다). 프로젝트 아래가 아니라 팀 설정이다.
# 등록·수정·삭제·연결 확인 경로는 여기 없다 — 운영자 콘솔(`/api/ops/mcp/`)로
# 옮겼다(2026-08-18). 화면에서만 감추면 API 는 그대로 열려 있게 된다.
urlpatterns = [
    path("servers/", McpServerListAPIView.as_view(), name="api_mcp_servers"),
]
