from django.urls import include, path

urlpatterns = [
    path("api/", include("apps.accounts.api_urls")),
    path("api/agents/", include("apps.agents.api_urls")),
    path("api/chat/", include("apps.chat.api_urls")),
    path("api/mcp/", include("apps.mcp.api_urls")),
    path("api/", include("apps.connectors.api_urls")),
    path("api/", include("apps.projects.api_urls")),
    path("api/", include("apps.people.api_urls")),
    path("api/", include("apps.personal_files.api_urls")),
    path("api/ops/", include("apps.ops.api_urls")),
]
