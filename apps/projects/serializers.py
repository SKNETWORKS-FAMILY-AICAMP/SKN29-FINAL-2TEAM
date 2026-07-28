"""현재 프로젝트·배정 실행 SQL 스키마의 입력 검증과 API 표현."""

from typing import Any

from rest_framework import serializers


class ProjectCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    status = serializers.ChoiceField(
        choices=("DRAFT", "ACTIVE", "ARCHIVED"),
        default="DRAFT",
    )
    tz = serializers.CharField(max_length=50, default="Asia/Seoul")
    owner_account_id = serializers.CharField(
        max_length=5,
        allow_null=True,
        required=False,
        default=None,
    )


class AssignmentRunCreateSerializer(serializers.Serializer):
    snapshot_id = serializers.CharField(max_length=5)
    readiness_id = serializers.CharField(
        max_length=5,
        allow_null=True,
        required=False,
        default=None,
    )
    requested_by = serializers.CharField(
        max_length=5,
        allow_null=True,
        required=False,
        default=None,
    )
    model_version = serializers.CharField(
        max_length=30,
        allow_null=True,
        required=False,
        default=None,
    )
    policy_version = serializers.CharField(
        max_length=30,
        allow_null=True,
        required=False,
        default=None,
    )


def project_response(row: dict[str, Any]) -> dict[str, Any]:
    """현재 SQL 필드와 기존 프론트 호환 필드를 함께 반환한다."""

    return {
        "proj_id": row["proj_id"],
        "project_id": row["proj_id"],
        "name": row["name"],
        "code": row["proj_id"],
        "description": "",
        "status": row["status"],
        "tz": row["tz"],
        "timezone": row["tz"],
        "owner_account_id": row["owner_account_id"],
        "owner": row["owner_account_id"],
        "owner_name": row.get("owner_name"),
        "created_at": "",
        "updated_at": "",
    }


def assignment_run_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "project_id": row.get("proj_id"),
        "snapshot_id": row["snapshot_id"],
        "readiness_id": row["readiness_id"],
        "model_version": row["model_version"],
        "policy_version": row["policy_version"],
        "status": row["status"],
        "requested_by": row["requested_by"],
    }
