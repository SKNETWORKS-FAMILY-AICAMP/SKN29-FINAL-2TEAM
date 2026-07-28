from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class ProjectUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("프로젝트 플랫폼", {"fields": ("display_name", "role")} ),)
    list_display = ("username", "display_name", "email", "role", "is_staff", "is_active")
