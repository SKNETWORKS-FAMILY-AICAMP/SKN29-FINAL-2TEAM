"""현재 프로젝트·배정 실행 SQL 스키마의 입력 검증과 API 표현."""

from datetime import datetime
from typing import Any

from rest_framework import serializers

from apps.connectors.clients import MAX_SCAN_DEPTH

class ProjectCreateSerializer(serializers.Serializer):
    """소유자는 요청이 아니라 로그인 토큰에서 정한다."""

    name = serializers.CharField(max_length=200)
    # 무엇을 하는 프로젝트인가. 기준 문서 후보를 찾는 질의가 이름과 이 문장으로
    # 만들어진다 — 비워도 되지만 그러면 후보가 이름 하나로만 뽑힌다.
    description = serializers.CharField(
        max_length=500, required=False, allow_blank=True, allow_null=True, default=None
    )
    status = serializers.ChoiceField(
        choices=("DRAFT", "ACTIVE", "ARCHIVED"),
        default="DRAFT",
    )
    tz = serializers.CharField(max_length=50, default="Asia/Seoul")

class PrimaryCandidateSerializer(serializers.Serializer):
    """기준 문서 후보를 찾을 질의.

    프로젝트를 아직 안 만든 상태에서도 부를 수 있게 `proj_id` 를 받지 않는다 —
    만들기 전에 "이 이름으로 찾으면 무엇이 나오나"를 보여 주는 편이, 만들고 나서
    아무것도 없다고 말하는 것보다 낫다.
    """

    name = serializers.CharField(max_length=200)
    description = serializers.CharField(
        max_length=500, required=False, allow_blank=True, allow_null=True, default=""
    )

class ProjectStatusSerializer(serializers.Serializer):
    """상태 변경. 「완료 처리」와 그 되돌리기가 쓴다.

    `DRAFT`는 받지 않는다 — 온보딩이 만들다 만 프로젝트를 뜻하던 값이고, 이제
    온보딩은 프로젝트를 만들지 않는다. 되돌릴 곳은 `ACTIVE`다.
    """

    status = serializers.ChoiceField(choices=("ACTIVE", "ARCHIVED"))

class TeamFolderReplaceSerializer(serializers.Serializer):
    """팀이 읽을 Drive 폴더의 전체 선택 상태. 빈 목록은 전부 해제한다는 뜻이다."""

    external_folder_ids = serializers.ListField(
        child=serializers.CharField(max_length=255),
        allow_empty=True,
    )
    # {폴더 id: Drive가 알려준 이름}. 화면이 id 대신 '01_기획'을 보여줄 수 있게
    # 고를 때 함께 저장한다. 안 보내면 이전 값을 지킨다.
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

class JiraProjectSelectionSerializer(serializers.Serializer):
    project_key = serializers.CharField(max_length=255)
    # Jira가 알려준 이름. 이것이 곧 우리 프로젝트 이름이 된다.
    name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")

class JiraProjectRegisterSerializer(serializers.Serializer):
    """고른 Jira 프로젝트 전체. 하나가 프로젝트 하나로 등록된다(1:1).

    빈 목록은 "이 팀이 읽을 Jira 프로젝트가 없다"는 뜻이라 허용한다 — 잘못
    고른 것을 되돌릴 방법이 있어야 한다.
    """

    projects = serializers.ListField(
        child=JiraProjectSelectionSerializer(),
        allow_empty=True,
    )

class DocumentRegisterEntrySerializer(serializers.Serializer):
    file_id = serializers.CharField(max_length=255)
    # 안 보내면 폴더에 지정된 역할을 물려받는다.

class DocumentRemoveSerializer(serializers.Serializer):
    """Drive 에서 사라진 문서를 내린다. 사용자가 확인한 것만 온다."""

    doc_ids = serializers.ListField(
        child=serializers.CharField(max_length=5), allow_empty=False
    )

def missing_document_response(row: dict[str, Any]) -> dict[str, Any]:
    """Drive 스캔에 안 잡히는 등록 문서 한 줄.

    프로젝트 정보를 함께 준다. 기준 문서가 사라졌다는 것은 그 프로젝트의 업무
    추출 근거가 없어졌다는 뜻이라, 내리기 전에 사람이 알아야 한다.
    """

    return {
        "doc_id": row["doc_id"],
        "file_name": row.get("file_name"),
        "mime_type": row.get("mime_type"),
        "proj_id": row.get("proj_id"),
        "project_name": row.get("project_name"),
        # NULL(팀 문서 풀) / 'PRIMARY'(기준 문서) / 'SUB'(근거 문서)
        "doc_role": row.get("doc_role"),
    }

class DocumentRegisterSerializer(serializers.Serializer):
    """신규 파일 목록에서 고른 것만 등록한다. 이름·형식은 서버가 Drive에서 다시 읽는다."""

    files = serializers.ListField(child=DocumentRegisterEntrySerializer(), allow_empty=False)

def project_response(
    row: dict[str, Any],
    progress: dict[str, Any] | None = None,
    *,
    last_sync: datetime | None = None,
    has_jira_source: bool = False,
) -> dict[str, Any]:
    """현재 SQL 필드와 기존 프론트 호환 필드를 함께 반환한다.

    `progress`는 목록 화면이 쓰는 Jira 집계다. 프로젝트 단건 조회에서는 주지 않고
    `null`로 둔다 — 화면이 "아직 안 읽었다"와 "집계할 업무가 없다"를 구분해야 한다.

    `last_sync_at`이 `null`인 경우가 두 가지라 `has_jira_source`로 갈라 준다.
    읽을 Jira 소스가 없는 것(갱신 버튼을 줄 이유가 없다)과, 소스는 있는데 아직
    안 읽은 것(눌러야 한다)은 화면에서 다르게 보여야 한다.

    `created_at`이 없는 프로젝트가 있다. 컬럼이 생기기 전에 만들어진 행이고,
    모르는 날짜를 지어내지 않으려고 `null`로 내려보낸다.
    """

    created_at = row.get("created_at")

    return {
        "last_sync_at": last_sync.isoformat() if last_sync else None,
        "has_jira_source": has_jira_source,
        "proj_id": row["proj_id"],
        "project_id": row["proj_id"],
        "name": row["name"],
        "description": row.get("description"),
        "code": row["proj_id"],
        "status": row["status"],
        "tz": row["tz"],
        "timezone": row["tz"],
        "owner_account_id": row["owner_account_id"],
        "owner": row["owner_account_id"],
        "owner_name": row.get("owner_name"),
        "created_at": created_at.isoformat() if created_at else None,
        "progress": progress,
    }

def project_source_response(row: dict[str, Any]) -> dict[str, Any]:
    last_sync_at = row.get("last_sync_at")
    return {
        "last_sync_at": last_sync_at.isoformat() if last_sync_at else None,
        "proj_source_id": row["proj_source_id"],
        "proj_id": row["proj_id"],
        "conn_id": row["conn_id"],
        "source_type": row["source_type"],
        "external_source_id": row["external_source_id"],
        "display_name": row.get("display_name"),
        "sync_status": row["sync_status"],
    }

def exist_task_response(row: dict[str, Any], persons: dict[str, Any]) -> dict[str, Any]:
    """Jira 이슈 한 건을 상세 화면의 업무 한 줄로.

    `summary`는 `summary` 컬럼이 생기기 전에 적재된 행에 없다. 지어내지 않고
    `null`로 두면 화면이 이슈 키로 대신한다.

    담당자 이름은 HR에서 왔다. 매핑이 안 된 이슈도 목록에서 빼지 않는다 —
    빼면 합계가 조용히 줄어 목록과 진행률이 어긋난다.
    """

    person_id = row.get("assignee_person_id")
    due_at = row.get("due_at")

    return {
        "exist_task_id": row["exist_task_id"],
        "jira_issue_id": row["jira_issue_id"],
        "summary": row.get("summary"),
        "assignee_person_id": person_id,
        "assignee_name": (persons.get(person_id) or {}).get("name") if person_id else None,
        # 표시용 상태와 로직용 카테고리를 함께 준다. 화면은 카테고리로 묶고
        # 사람에게는 Jira가 쓰는 말을 보여준다.
        "status": row.get("status"),
        "status_category": row.get("status_category"),
        "due_at": due_at.isoformat() if due_at else None,
        "estimate": float(row["estimate"]) if row.get("estimate") is not None else None,
        "remaining": float(row["remaining"]) if row.get("remaining") is not None else None,
    }

def extracted_task_response(row: dict[str, Any]) -> dict[str, Any]:
    """기준 문서에서 뽑아 등록한 우리 업무 한 줄(`task`).

    Jira 이슈(`exist_task`)와 컬럼이 다르다. 담당자가 없고, 상태는 우리
    `PROPOSED / CONFIRMED / REJECTED` 다. **비어 있는 값을 0 이나 「미정」으로
    채우지 않는다** — 문서에 없어서 비운 것과 0 은 다르다.
    """

    due_at = row.get("due_at")
    generated_at = row.get("generated_at")

    return {
        "task_id": row["task_id"],
        "title": row["task_name"],
        "required_role": row.get("req_role"),
        "effort_hours": float(row["effort"]) if row.get("effort") is not None else None,
        "due_at": due_at.isoformat() if due_at else None,
        "priority": row.get("priority"),
        "status": row["status"],
        "model_ver": row.get("model_ver"),
        "generated_at": generated_at.isoformat() if generated_at else None,
    }

class TaskExtractionCreateSerializer(serializers.Serializer):
    primary_document_id = serializers.CharField(max_length=5)

class ProjectSourceDocumentSerializer(serializers.Serializer):
    """기준 문서 1건. 근거 문서는 사람이 고르지 않으므로 받지 않는다.

    **null 은 해제다.** 잘못 고른 문서를 되돌릴 방법이 없어서, 한 번 묶으면
    다른 문서로 바꾸는 것만 되고 「없음」으로는 못 갔다(2026-08-12 QA). 바꿀
    문서가 없으면 사람은 갇힌다.
    """

    primary_document_id = serializers.CharField(max_length=5, allow_null=True)

def pipeline_document_response(row: dict[str, Any]) -> dict[str, Any]:
    """기준 문서 선택 화면이 쓰는 한 줄.

    `downloaded`와 `search_ready`를 나눠서 준다. 「원문을 아직 안 받았다」와
    「받았지만 파싱·임베딩이 안 됐다」는 사용자가 할 행동이 다르다 — 앞은 문서
    등록 화면으로, 뒤는 「문서 처리」 버튼으로 간다.
    """

    modified_at = row.get("src_modified_at")

    return {
        "doc_id": row["doc_id"],
        "file_name": row.get("file_name"),
        "mime_type": row.get("mime_type"),
        "proj_id": row.get("proj_id"),
        # NULL(팀 문서 풀) / 'PRIMARY'(기준 문서) / 'SUB'(근거 문서)
        "doc_role": row.get("doc_role"),
        "downloaded": bool(row.get("storage_key")),
        "search_ready": bool(row.get("search_ready")),
        "src_modified_at": modified_at.isoformat() if modified_at else None,
    }

def deadline_response(
    row: dict[str, Any],
    persons: dict[str, Any],
    *,
    days: int,
) -> dict[str, Any]:
    """마감이 걸린 업무 한 건.

    `days`를 서버가 계산해서 준다. `due_at`이 TIMESTAMPTZ라 브라우저에서 빼면
    시간대에 따라 하루가 밀린다 — 「오늘 마감」이 「어제 마감」으로 보이는 것은
    이 화면에서 바로 오판으로 이어진다. 음수가 지연이다.

    어느 프로젝트 것인지 함께 준다. 「KAN-31 지연」만으로는 어느 쪽을 밀지 판단할
    수 없다.
    """

    person_id = row.get("assignee_person_id")

    return {
        "exist_task_id": row["exist_task_id"],
        "jira_issue_id": row["jira_issue_id"],
        "summary": row.get("summary"),
        "assignee_name": (persons.get(person_id) or {}).get("name") if person_id else None,
        "due_at": row["due_at"].isoformat(),
        "days": days,
        "proj_id": row["proj_id"],
        "project_name": row.get("project_name") or row.get("project_key"),
    }

def team_folder_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "team_folder_id": row["team_folder_id"],
        "team_id": row["team_id"],
        "conn_id": row["conn_id"],
        "external_folder_id": row["external_folder_id"],
        "display_name": row.get("display_name"),
        "max_depth": row.get("max_depth"),
    }

def document_response(row: dict[str, Any]) -> dict[str, Any]:
    modified_at = row.get("src_modified_at")
    return {
        "doc_id": row["doc_id"],
        "team_id": row.get("team_id"),
        # 아직 어느 프로젝트의 문서인지 지정되지 않았으면 null이다.
        "proj_id": row.get("proj_id"),
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

    상태는 **실제로 실패한 건이 있을 때만** `PARTIAL`이다. 미지원 형식이라 등록에서
    빠진 것(`skipped`)은 걸러진 것이지 실패가 아니라서 여기 들어가지 않는다 —
    건수는 `payload`에 그대로 있으니 화면이 따로 보여준다.

    표시 문구는 화면이 정한다. 여기서 한국어를 만들면 `blocked_reason`처럼 코드로
    내려보내는 다른 응답과 규칙이 어긋난다.
    """

    payload = row.get("payload") or {}
    occurred_at = row["occurred_at"]

    return {
        "audit_id": row["audit_id"],
        "action": row["action"],
        "occurred_at": occurred_at.isoformat() if occurred_at else None,
        "actor_display_name": row.get("actor_display_name"),
        "status": "PARTIAL" if (payload.get("failed") or 0) else "OK",
        "payload": payload,
    }
