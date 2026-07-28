from django.contrib import admin

from .models import AnalysisRun, Project, ProjectDocument


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "status", "owner", "updated_at")
    list_filter = ("status",)
    search_fields = ("code", "name")


@admin.register(ProjectDocument)
class ProjectDocumentAdmin(admin.ModelAdmin):
    list_display = ("file_name", "project", "document_role", "processing_status", "updated_at")
    list_filter = ("source_type", "document_role", "processing_status")


@admin.register(AnalysisRun)
class AnalysisRunAdmin(admin.ModelAdmin):
    list_display = ("run_id", "project", "status", "readiness_status", "created_at")
    list_filter = ("status", "readiness_status")
