from django.contrib import admin

from .models import IdentityLink, Organization, Person, PersonAbsence, PersonSkill, ResponsibilityLevel, Skill, WorkSchedule


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "parent", "is_active")
    search_fields = ("name", "code")


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("name", "employee_id", "organization", "job_role", "employment_status", "fte")
    list_filter = ("organization", "employment_status", "is_active")
    search_fields = ("name", "employee_id", "email")


admin.site.register([ResponsibilityLevel, Skill, PersonSkill, WorkSchedule, PersonAbsence, IdentityLink])
