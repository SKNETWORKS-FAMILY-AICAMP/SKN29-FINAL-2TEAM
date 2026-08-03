"""연결된 커넥터로 외부 데이터를 조회한다.

`oauth.py`는 provider 프로토콜만 다루고 저장을 모른다. 여기서 저장된 암호문을
꺼내 만료를 확인하고, 필요하면 갱신해 다시 저장한 뒤 실제 API를 호출한다.

조회 전용이다. 어떤 폴더·프로젝트를 쓸지 고른 결과를 저장하는 것은
`proj_source`(프로젝트 단위)의 일이라 여기서 다루지 않는다
(`Jira_Drive_커넥터_연결_설계.md` §4).
"""

from datetime import UTC, datetime
from typing import Any

import requests

from backend.db import ConnectorRepository

from .oauth import (
    GOOGLE_DRIVE,
    JIRA,
    GoogleDriveOAuth,
    JiraOAuth,
    OAuthError,
    decrypt_credential,
    encrypt_credential,
)

# 호출 도중 만료되는 것을 피하려고 조금 이르게 갱신한다.
_REFRESH_MARGIN_SECONDS = 60

_PROVIDERS = {GOOGLE_DRIVE: GoogleDriveOAuth, JIRA: JiraOAuth}

DRIVE_FILES_ENDPOINT = "https://www.googleapis.com/drive/v3/files"
DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"
# Drive가 내 드라이브 최상단에 부여하는 별칭. 실제 폴더 id 대신 쓸 수 있다.
DRIVE_ROOT_ID = "root"
_DRIVE_PAGE_SIZE = 100
_DRIVE_MAX_PAGES = 10
# "제한 없음"으로 탐색할 때 API 호출이 무한정 늘어나지 않게 막는다.
_DRIVE_MAX_FOLDERS = 200
# `proj_source.max_depth`가 받아들이는 상한. 이보다 깊으면 사실상 제한 없음이다.
MAX_SCAN_DEPTH = 10
# 원문 다운로드는 목록 조회보다 오래 걸린다(수십 MB PDF).
_DOWNLOAD_TIMEOUT_SECONDS = 120

# Google 문서에는 내려받을 실체 파일이 없다. 파서가 다룰 수 있는 Office 형식으로
# 내보내야 한다.
DRIVE_EXPORT_MIMES = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ),
}

# 본문에서 업무를 뽑아낼 수 있는 형식. 이미지·영상·압축 파일은 지금 파서로
# 다룰 수 없어 목록에 보이되 제외 표시를 한다.
SUPPORTED_DOC_MIMES = frozenset(
    {
        "application/vnd.google-apps.document",
        "application/vnd.google-apps.presentation",
        "application/vnd.google-apps.spreadsheet",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/plain",
        "text/markdown",
        "text/csv",
    }
)


def _expired(credential: dict[str, Any]) -> bool:
    raw = credential.get("expires_at")
    if not isinstance(raw, str):
        return True
    try:
        expires_at = datetime.fromisoformat(raw)
    except ValueError:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return (expires_at - datetime.now(UTC)).total_seconds() <= _REFRESH_MARGIN_SECONDS


def credential_for(*, account_id: str, connector_type: str) -> dict[str, Any]:
    """유효한 자격증명. 만료가 임박하면 갱신해서 저장까지 마친 뒤 돌려준다."""

    provider = _PROVIDERS[connector_type]
    credential = decrypt_credential(
        ConnectorRepository.get_credential(account_id=account_id, connector_type=connector_type)
    )
    if not _expired(credential):
        return credential

    try:
        refreshed = provider.refresh(credential)
    except OAuthError:
        # 갱신이 실패하면 화면이 재연결을 유도할 수 있도록 상태를 남긴다.
        ConnectorRepository.mark_expired(account_id=account_id, connector_type=connector_type)
        raise

    ConnectorRepository.update_credential(
        account_id=account_id,
        connector_type=connector_type,
        encrypted_credential=encrypt_credential(refreshed),
    )
    return refreshed


def _drive_children(headers: dict[str, str], *, query: str, fields: str, failure: str) -> list[Any]:
    """페이지를 끝까지 따라간 자식 목록. Drive는 한 번에 최대 100건만 준다."""

    items: list[Any] = []
    page_token: str | None = None
    for _ in range(_DRIVE_MAX_PAGES):
        params = {
            "q": query,
            "fields": f"nextPageToken,files({fields})",
            "pageSize": _DRIVE_PAGE_SIZE,
            "orderBy": "name",
        }
        if page_token:
            params["pageToken"] = page_token
        try:
            response = requests.get(DRIVE_FILES_ENDPOINT, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise OAuthError(failure) from exc

        page = payload.get("files")
        if not isinstance(page, list):
            raise OAuthError("Google Drive가 예상한 형식으로 응답하지 않았습니다.")
        items.extend(item for item in page if isinstance(item, dict) and isinstance(item.get("id"), str))

        page_token = payload.get("nextPageToken")
        if not isinstance(page_token, str):
            break

    return items


def list_drive_folders(*, account_id: str, parent_id: str = DRIVE_ROOT_ID) -> list[dict[str, Any]]:
    """`parent_id` 바로 아래의 폴더 목록.

    Drive 전체를 한 번에 내려주면 무관한 폴더에 묻힌다(실제 계정에서 473개).
    한 단계씩 내려가면 화면이 필요한 만큼만 조회한다.
    """

    credential = credential_for(account_id=account_id, connector_type=GOOGLE_DRIVE)
    folders = _drive_children(
        {"Authorization": f"Bearer {credential['access_token']}"},
        query=f"'{parent_id}' in parents and mimeType = '{DRIVE_FOLDER_MIME}' and trashed = false",
        fields="id,name,modifiedTime",
        failure="Google Drive 폴더 목록을 가져오지 못했습니다.",
    )
    return [
        {
            "folder_id": item["id"],
            "name": item.get("name") or "(이름 없음)",
            "modified_at": item.get("modifiedTime"),
        }
        for item in folders
    ]


def list_drive_files(
    *,
    account_id: str,
    parent_id: str,
    max_depth: int | None = 1,
) -> list[dict[str, Any]]:
    """`parent_id` 아래의 파일. `max_depth`만큼 하위 폴더를 따라 내려간다.

    `max_depth`는 선택한 폴더를 1단계로 센다. 1이면 직속 파일만, `None`이면
    제한 없음(`_DRIVE_MAX_FOLDERS`까지). 각 파일에는 어느 폴더에서 왔는지
    `folder_path`를 붙인다 — 재귀로 모으면 평면 목록만 봐서는 알 수 없다.

    파싱할 수 없는 형식도 목록에는 넣는다. 사용자가 "왜 내 파일이 없지"를
    묻지 않게 하려면 제외된 사실을 보여주는 편이 낫다.
    """

    credential = credential_for(account_id=account_id, connector_type=GOOGLE_DRIVE)
    headers = {"Authorization": f"Bearer {credential['access_token']}"}

    files: list[dict[str, Any]] = []
    # (폴더 id, 표시 경로, 이 폴더의 깊이)
    pending: list[tuple[str, str, int]] = [(parent_id, "", 1)]
    visited = 0

    while pending and visited < _DRIVE_MAX_FOLDERS:
        folder_id, path, depth = pending.pop(0)
        visited += 1

        for item in _drive_children(
            headers,
            query=f"'{folder_id}' in parents and mimeType != '{DRIVE_FOLDER_MIME}' and trashed = false",
            fields="id,name,mimeType,modifiedTime",
            failure="Google Drive 파일 목록을 가져오지 못했습니다.",
        ):
            files.append(
                {
                    "file_id": item["id"],
                    "name": item.get("name") or "(이름 없음)",
                    "mime_type": item.get("mimeType"),
                    "modified_at": item.get("modifiedTime"),
                    "supported": item.get("mimeType") in SUPPORTED_DOC_MIMES,
                    "folder_path": path,
                }
            )

        if max_depth is not None and depth >= max_depth:
            continue

        for child in _drive_children(
            headers,
            query=f"'{folder_id}' in parents and mimeType = '{DRIVE_FOLDER_MIME}' and trashed = false",
            fields="id,name",
            failure="Google Drive 폴더 목록을 가져오지 못했습니다.",
        ):
            name = child.get("name") or "(이름 없음)"
            pending.append((child["id"], f"{path}/{name}" if path else name, depth + 1))

    return files


def get_drive_folders(*, account_id: str, folder_ids: list[str]) -> list[dict[str, Any]]:
    """id로 폴더를 되짚어 이름을 채운다.

    `proj_source`에는 폴더 id만 남으므로, 저장된 선택을 화면에 다시 보여주려면
    이름을 Drive에서 다시 가져와야 한다. Drive 검색식은 id 비교를 지원하지 않아
    개별 조회를 쓴다 — 선택한 폴더 수만큼이라 몇 건이다.
    """

    if not folder_ids:
        return []

    credential = credential_for(account_id=account_id, connector_type=GOOGLE_DRIVE)
    headers = {"Authorization": f"Bearer {credential['access_token']}"}

    folders = []
    for folder_id in folder_ids:
        try:
            response = requests.get(
                f"{DRIVE_FILES_ENDPOINT}/{folder_id}",
                headers=headers,
                params={"fields": "id,name,modifiedTime"},
                timeout=15,
            )
            # 지워졌거나 권한이 사라진 폴더는 목록에서 조용히 빠진다.
            if response.status_code == 404 or response.status_code == 403:
                continue
            response.raise_for_status()
            item = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise OAuthError("Google Drive 폴더 정보를 가져오지 못했습니다.") from exc

        if isinstance(item, dict) and isinstance(item.get("id"), str):
            folders.append(
                {
                    "folder_id": item["id"],
                    "name": item.get("name") or "(이름 없음)",
                    "modified_at": item.get("modifiedTime"),
                }
            )
    return folders


def download_drive_file(*, account_id: str, file_id: str, mime_type: str | None) -> dict[str, Any]:
    """원문 바이트와 리비전 id.

    Google 문서(Docs·Sheets·Slides)는 실체 파일이 없어 `alt=media`로 받을 수 없고
    Office 형식으로 **내보내야** 한다. 목록 화면이 이 형식들을 "파싱 가능"으로
    표시하므로, 여기서 못 받으면 고를 수는 있는데 받을 수 없는 문서가 된다.
    """

    credential = credential_for(account_id=account_id, connector_type=GOOGLE_DRIVE)
    headers = {"Authorization": f"Bearer {credential['access_token']}"}
    export_to = DRIVE_EXPORT_MIMES.get(mime_type or "")

    try:
        # 리비전은 본문과 같은 시점의 값이어야 해서 먼저 읽는다. Google 문서에는
        # md5가 없으므로 변경 감지는 우리가 계산하는 content_hash로 한다.
        meta = requests.get(
            f"{DRIVE_FILES_ENDPOINT}/{file_id}",
            headers=headers,
            params={"fields": "id,headRevisionId,size"},
            timeout=15,
        )
        meta.raise_for_status()
        revision = meta.json().get("headRevisionId")

        if export_to:
            response = requests.get(
                f"{DRIVE_FILES_ENDPOINT}/{file_id}/export",
                headers=headers,
                params={"mimeType": export_to},
                timeout=_DOWNLOAD_TIMEOUT_SECONDS,
            )
        else:
            response = requests.get(
                f"{DRIVE_FILES_ENDPOINT}/{file_id}",
                headers=headers,
                params={"alt": "media"},
                timeout=_DOWNLOAD_TIMEOUT_SECONDS,
            )
        response.raise_for_status()
    except (requests.RequestException, ValueError) as exc:
        raise OAuthError("Google Drive에서 원문을 내려받지 못했습니다.") from exc

    return {
        "content": response.content,
        "mime_type": export_to or mime_type,
        "revision": revision if isinstance(revision, str) else None,
    }


# Jira 상태 표시 이름은 사이트·프로젝트마다 다르다. 실측에서 같은 카테고리인데
# KAN은 '해야 할 일', AIP는 '할 일'로 왔고 statusCategory.name마저 한국어로
# 지역화된다. 사이트가 바뀌어도 그대로인 값은 key 하나뿐이라 이것만 옮긴다.
_JIRA_STATUS_CATEGORY = {
    "new": "TO_DO",
    "indeterminate": "IN_PROGRESS",
    "done": "DONE",
}
_JIRA_SEARCH_PAGE_SIZE = 100
# 한 프로젝트가 이보다 많으면 페이지를 더 따라가지 않는다(목록 조회와 같은 방침).
_JIRA_MAX_PAGES = 10


def list_jira_projects(*, account_id: str) -> list[dict[str, Any]]:
    """연결된 Jira 사이트의 프로젝트 목록."""

    credential = credential_for(account_id=account_id, connector_type=JIRA)
    cloud_id = credential.get("cloud_id")
    if not isinstance(cloud_id, str):
        raise OAuthError("연결된 Jira 사이트 정보를 찾을 수 없습니다. 다시 연결해 주세요.")

    try:
        response = requests.get(
            f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/project/search",
            headers={
                "Authorization": f"Bearer {credential['access_token']}",
                "Accept": "application/json",
            },
            # description·lead는 기본 응답에 없어서 expand로 요청해야 한다.
            params={"maxResults": 100, "orderBy": "name", "expand": "description,lead"},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise OAuthError("Jira 프로젝트 목록을 가져오지 못했습니다.") from exc

    values = payload.get("values")
    if not isinstance(values, list):
        raise OAuthError("Jira가 예상한 형식으로 응답하지 않았습니다.")

    projects = []
    for item in values:
        if not isinstance(item, dict) or not isinstance(item.get("key"), str):
            continue
        lead = item.get("lead")
        projects.append(
            {
                "project_key": item["key"],
                "project_id": item.get("id"),
                "name": item.get("name") or item["key"],
                "description": item.get("description") or None,
                "project_type": item.get("projectTypeKey"),
                "lead_name": lead.get("displayName") if isinstance(lead, dict) else None,
                "avatar_url": (item.get("avatarUrls") or {}).get("48x48")
                if isinstance(item.get("avatarUrls"), dict)
                else None,
            }
        )
    return projects


def _hours(seconds: Any) -> float | None:
    """Jira의 초 단위 공수를 시간으로. `NUMERIC(6,2)`에 맞춰 반올림한다."""

    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        return None
    return round(seconds / 3600, 2)


def _dict_at(source: dict[str, Any], key: str) -> dict[str, Any]:
    value = source.get(key)
    return value if isinstance(value, dict) else {}


def _jira_issue_row(item: dict[str, Any]) -> dict[str, Any]:
    """검색 응답 한 건을 `exist_task` 한 행으로."""

    fields = _dict_at(item, "fields")
    status = _dict_at(fields, "status")
    category = _dict_at(status, "statusCategory")
    tracking = _dict_at(fields, "timetracking")

    return {
        "jira_issue_id": item["key"],
        # 사람이 보는 값. 사이트마다 달라서 조건문에 쓰면 안 된다.
        "status": status.get("name"),
        # 모르는 key는 None으로 둔다. 임의로 TO_DO에 밀어넣으면 부하가 조용히 늘어난다.
        "status_category": _JIRA_STATUS_CATEGORY.get(category.get("key")),
        "priority": _dict_at(fields, "priority").get("name"),
        # 프로필이 비공개면 응답에 아예 없다. 그때도 행은 버리지 않는다.
        "assignee_email": _dict_at(fields, "assignee").get("emailAddress"),
        "due_at": fields.get("duedate"),
        # Jira 표준 이슈에는 시작일 필드가 없다. `fields.created`는 "이슈가 만들어진
        # 날"이지 "일을 시작한 날"이 아니라서 여기에 넣지 않는다 — 넣으면 없는
        # 정보를 있는 것처럼 만든다. 지금 부하 계산은 start_at을 쓰지 않는다.
        "start_at": None,
        "estimate": _hours(tracking.get("originalEstimateSeconds")),
        "remaining": _hours(tracking.get("remainingEstimateSeconds")),
        "spent": _hours(tracking.get("timeSpentSeconds")),
    }


def search_jira_issues(*, account_id: str, project_key: str) -> list[dict[str, Any]]:
    """프로젝트의 미완료 이슈. 담당자·상태·마감·공수만 추린다."""

    credential = credential_for(account_id=account_id, connector_type=JIRA)
    cloud_id = credential.get("cloud_id")
    if not isinstance(cloud_id, str):
        raise OAuthError("연결된 Jira 사이트 정보를 찾을 수 없습니다. 다시 연결해 주세요.")

    headers = {
        "Authorization": f"Bearer {credential['access_token']}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    # 완료된 이슈는 부하에 안 잡힌다. 표시 이름이 아니라 표준 카테고리로 거른다.
    body: dict[str, Any] = {
        "jql": f'project = "{project_key}" AND statusCategory != Done ORDER BY key',
        "fields": ["assignee", "status", "priority", "duedate", "timetracking"],
        "maxResults": _JIRA_SEARCH_PAGE_SIZE,
    }

    issues: list[dict[str, Any]] = []
    next_token: str | None = None
    for _ in range(_JIRA_MAX_PAGES):
        page_body = dict(body)
        if next_token:
            page_body["nextPageToken"] = next_token
        try:
            # 구 `GET /rest/api/3/search`는 Jira Cloud에서 제거됐다. 새 엔드포인트는
            # POST이고 페이지네이션도 startAt이 아니라 nextPageToken이다 —
            # startAt으로 짜면 오류 없이 첫 페이지만 돌아온다.
            response = requests.post(
                f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/search/jql",
                headers=headers,
                json=page_body,
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise OAuthError(f"Jira 이슈를 가져오지 못했습니다({project_key}).") from exc

        page = payload.get("issues")
        if not isinstance(page, list):
            raise OAuthError("Jira가 예상한 형식으로 응답하지 않았습니다.")
        issues.extend(
            _jira_issue_row(item)
            for item in page
            if isinstance(item, dict) and isinstance(item.get("key"), str)
        )

        next_token = payload.get("nextPageToken")
        if not isinstance(next_token, str):
            break

    return issues
