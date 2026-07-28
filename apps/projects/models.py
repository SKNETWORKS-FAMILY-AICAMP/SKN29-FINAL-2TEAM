import uuid

from django.conf import settings
from django.db import models


class ProjectStatus(models.TextChoices):
    DRAFT = "DRAFT", "초안"
    ACTIVE = "ACTIVE", "진행 중"
    ARCHIVED = "ARCHIVED", "보관"


class AnalysisRunStatus(models.TextChoices):
    CREATED = "CREATED", "생성됨"
    INGESTING = "INGESTING", "문서 수집 중"
    STRUCTURING = "STRUCTURING", "지식 모델 생성 중"
    SNAPSHOT_CREATED = "SNAPSHOT_CREATED", "스냅샷 생성됨"
    READINESS_CHECKED = "READINESS_CHECKED", "준비 상태 확인됨"
    TASK_REVIEW_REQUIRED = "TASK_REVIEW_REQUIRED", "PM 업무 확인 필요"
    BLOCKED = "BLOCKED", "차단됨"
    FAILED = "FAILED", "실패"


class Project(models.Model):
    project_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    timezone = models.CharField(max_length=50, default="Asia/Seoul")
    status = models.CharField(max_length=30, choices=ProjectStatus.choices, default=ProjectStatus.DRAFT)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="owned_projects")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"[{self.code}] {self.name}"


class ProjectDocument(models.Model):
    document_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="documents")
    source_type = models.CharField(max_length=30, default="LOCAL")
    source_file_id = models.CharField(max_length=255, blank=True)
    file_name = models.CharField(max_length=255)
    declared_mime_type = models.CharField(max_length=150, blank=True)
    detected_format = models.CharField(max_length=50, blank=True)
    format_validation_status = models.CharField(max_length=20, default="UNKNOWN")
    version = models.CharField(max_length=100, default="v1")
    content_hash = models.CharField(max_length=100, blank=True)
    storage_key = models.CharField(max_length=500, blank=True)
    document_role = models.CharField(max_length=50, default="PROJECT_PLAN")
    processing_status = models.CharField(max_length=30, default="PENDING")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]


class AnalysisRun(models.Model):
    run_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="analysis_runs")
    status = models.CharField(max_length=40, choices=AnalysisRunStatus.choices, default=AnalysisRunStatus.CREATED)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    snapshot_as_of = models.DateTimeField(null=True, blank=True)
    readiness_status = models.CharField(max_length=30, default="PENDING")
    missing_data = models.JSONField(default=list, blank=True)
    limitations = models.JSONField(default=list, blank=True)
    assumptions = models.JSONField(default=list, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
