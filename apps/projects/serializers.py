from rest_framework import serializers

from .models import AnalysisRun, Project


class ProjectSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.display_name", read_only=True)

    class Meta:
        model = Project
        fields = ("project_id", "name", "code", "description", "timezone", "status", "owner", "owner_name", "created_at", "updated_at")
        read_only_fields = ("project_id", "owner", "created_at", "updated_at")


class AnalysisRunSerializer(serializers.ModelSerializer):
    project_id = serializers.UUIDField(source="project.project_id", read_only=True)

    class Meta:
        model = AnalysisRun
        fields = (
            "run_id",
            "project_id",
            "status",
            "snapshot_as_of",
            "readiness_status",
            "missing_data",
            "limitations",
            "assumptions",
            "error_message",
            "created_at",
            "updated_at",
        )
