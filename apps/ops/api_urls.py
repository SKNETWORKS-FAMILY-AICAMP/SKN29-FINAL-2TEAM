from django.urls import path

from .views.login import LoginView, LogoutView, MeView
from .views.overview import OverviewView

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="api_ops_auth_login"),
    path("auth/me/", MeView.as_view(), name="api_ops_auth_me"),
    path("auth/logout/", LogoutView.as_view(), name="api_ops_auth_logout"),
    path("overview/", OverviewView.as_view(), name="api_ops_overview"),
]
