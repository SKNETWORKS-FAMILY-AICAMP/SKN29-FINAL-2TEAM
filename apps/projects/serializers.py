"""현재 프로젝트·배정 실행 SQL 스키마의 입력 검증과 API 표현."""

from typing import Any

from rest_framework import serializers

from apps.connectors.clients import MAX_SCAN_DEPTH


class ProjectCreateSerializer(serializers.Serializer):
    """소유자는 요청이 아니라 로그인 토큰에서 정한다."""

    name = serializers.CharField(max_length=200)
    status = serializers.ChoiceField(
        choices=("DRAFT", "ACTIVE", "ARCHIVED"),
        default="DRAFT",
    )
    tz = serializers.CharField(max_length=50, default="Asia/Seoul")


class ProjectSourceReplaceSerializer(serializers.Serializer):
    """이 종류의 소스 전체 선택 상태. 빈 목록은 전부 해제한다는 뜻이다."""

    source_type = serializers.ChoiceField(choices=("DRIVE_FOLDER", "JIRA_PROJECT"))
    external_source_ids = serializers.ListField(
        child=serializers.CharField(max_length=255),
        allow_empty=True,
    )
    # {외부 id: 원본이 알려준 이름}. 화면이 'KAN'이 아니라 'SKN29_Final_2Team'을
    # 보여줄 수 있게 고를 때 함께 저장한다. 안 보내면 이전 값을 지킨다.
    display_names = serializers.DictField(
        child=serializers.CharField(max_length=255, allow_blank=True),
        required=False,
        default=dict,
    )
    # 폴더 탐색 깊이. 1이면 선택한 폴더만, null이면 제한 없음.
    # "하위 폴더 포함"을 끄는 것이 곧 1이다 — 별도 불리언을 두지 않는다.
    max_depth = serializers.IntegerField(
        min_value=1,
        max_value=MAX_SCAN_DEPTH,
        allow_null=True,
        required=False,
        default=1,
    )


DOC_ROLES = ("PLAN", "MEETING_NOTE", "DAILY_REPORT", "OTHER")


class DocumentRegisterEntrySerializer(serializers.Serializer):
    file_id = serializers.CharField(max_length=255)
    # 안 보내면 폴더에 지정된 역할을 물려받는다.
    doc_role = serializers.ChoiceField(choices=DOC_ROLES, required=False, allow_null=True)


class DocumentRegisterSerializer(serializers.Serializer):
    """신규 파일 목록에서 고른 것만 등록한다. 이름·형식은 서버가 Drive에서 다시 읽는다."""

    files = serializers.ListField(child=DocumentRegisterEntrySerializer(), allow_empty=False)


class DocumentRoleSaveSerializer(serializers.Serializer):
    """역할 지정 화면의 저장 내용.

    파일 목록과 이름은 받지 않는다 — 서버가 Drive에서 다시 읽는다. 클라이언트가
    보낸 메타데이터를 그대로 `doc`에 넣으면 실재하지 않는 문서가 생길 수 있다.
    """

    folder_roles = serializers.DictField(
        child=serializers.ChoiceField(choices=DOC_ROLES),
        allow_empty=True,
    )
    file_roles = serializers.DictField(
        child=serializers.ChoiceField(choices=DOC_ROLES),
        allow_empty=True,
        required=False,
        default=dict,
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


def project_source_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "proj_source_id": row["proj_source_id"],
        "proj_id": row["proj_id"],
        "conn_id": row["conn_id"],
        "source_type": row["source_type"],
        "external_source_id": row["external_source_id"],
        "display_name": row.get("display_name"),
        "sync_status": row["sync_status"],
        "default_doc_role": row.get("default_doc_role"),
        "max_depth": row.get("max_depth"),
    }


def document_response(row: dict[str, Any]) -> dict[str, Any]:
    modified_at = row.get("src_modified_at")
    return {
        "doc_id": row["doc_id"],
        "proj_id": row["proj_id"],
        "src_file_id": row["src_file_id"],
        "source_type": row["source_type"],
        "file_name": row["file_name"],
        "mime_type": row["mime_type"],
        "doc_role": row["doc_role"],
        "src_modified_at": modified_at.isoformat() if modified_at else None,
        # 원문을 받았는지만 알려준다. 저장소 키 자체는 서버 내부 사정이다.
        "downloaded": bool(row.get("storage_key")),
    }


def document_history_response(row: dict[str, Any]) -> dict[str, Any]:
    """`audit_log` 한 줄을 문서 처리 이력으로.

    실패가 섞였으면 `PARTIAL_RESULT`다 — 화면이 "완료"로만 보여주면 몇 건이
    빠졌는지 알 수 없다.
    """

    payload = row.get("payload") or {}
    failed = payload.get("failed") or payload.get("skipped") or 0
    occurred_at = row["occurred_at"]

    return {
        "audit_id": row["audit_id"],
        "action": row["action"],
        "occurred_at": occurred_at.isoformat() if occurred_at else None,
        "actor_display_name": row.get("actor_display_name"),
        "status": "PARTIAL_RESULT" if failed else "완료",
        "payload": payload,
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
