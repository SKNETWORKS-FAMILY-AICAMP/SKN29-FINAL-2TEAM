"""연결된 커넥터로 외부 데이터를 조회한다.

`oauth.py`는 provider 프로토콜만 다루고 저장을 모른다. 여기서 저장된 암호문을
꺼내 만료를 확인하고, 필요하면 갱신해 다시 저장한 뒤 실제 API를 호출한다.

조회 전용이다. 어떤 폴더·프로젝트를 쓸지 고른 결과를 저장하는 것은
`proj_source`(프로젝트 단위)의 일이라 여기서 다루지 않는다
(`Jira_Drive_커넥터_연결_설계.md` §4).
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

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

logger = logging.getLogger(__name__)

# 호출 도중 만료되는 것을 피하려고 조금 이르게 갱신한다.
_REFRESH_MARGIN_SECONDS = 60

_PROVIDERS = {GOOGLE_DRIVE: GoogleDriveOAuth, JIRA: JiraOAuth}

DRIVE_FILES_ENDPOINT = "https://www.googleapis.com/drive/v3/files"
DRIVE_CHANGES_ENDPOINT = "https://www.googleapis.com/drive/v3/changes"
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


#: 변경 한 번에 따라갈 페이지 수. 넘치면 남은 지점을 커서로 저장하고 멈춘다 —
#: 다음 회차가 거기서 이어받으므로 놓치는 변경은 없다.
_DRIVE_CHANGE_MAX_PAGES = 10


def drive_start_page_token(*, account_id: str) -> str:
    """**지금 이 시점**을 가리키는 커서.

    커서가 없을 때 한 번 부른다. 연결 이전의 변경까지 거슬러 올라갈 이유가 없다 —
    처음 등록은 폴더 스캔이 이미 하고, 여기서 필요한 것은 「이제부터」다.
    """

    credential = credential_for(account_id=account_id, connector_type=GOOGLE_DRIVE)
    try:
        response = requests.get(
            f"{DRIVE_CHANGES_ENDPOINT}/startPageToken",
            headers={"Authorization": f"Bearer {credential['access_token']}"},
            timeout=15,
        )
        response.raise_for_status()
        token = response.json().get("startPageToken")
    except (requests.RequestException, ValueError) as exc:
        raise OAuthError("Google Drive 변경 시작 지점을 받지 못했습니다.") from exc
    if not isinstance(token, str) or not token:
        raise OAuthError("Google Drive가 예상한 형식으로 응답하지 않았습니다.")
    return token


#: 채널을 얼마나 열어 둘까. Drive 의 `changes` 채널 상한이 1주일이고 **자동
#: 갱신이 없다** — 만료 전에 새로 열어 주는 것은 우리 몫이다.
#:
#: 상한을 그대로 쓰지 않고 6일로 잡는다. 갱신 작업이 하루에 한 번 돈다고 할 때,
#: 상한에 딱 맞추면 그 한 번을 놓치는 순간 구멍이 생긴다. 하루를 남겨 두면
#: **한 번쯤 걸러도 채널이 살아 있다.**
DRIVE_CHANNEL_TTL = timedelta(days=6)


def watch_drive_changes(*, account_id: str, page_token: str, callback_url: str, token: str) -> dict[str, Any]:
    """변경 알림 채널을 연다. 채널 id·resourceId·만료 시각을 돌려준다.

    **알림에는 무엇이 바뀌었는지가 안 담긴다.** 본문이 빈 POST 가 올 뿐이라,
    받은 쪽은 결국 `list_drive_changes` 를 불러야 한다. 그래서 이 채널이 없애는
    것은 「호출」이 아니라 **「언제 물을지 우리가 정해야 하는 것」**이다 —
    대화를 열 때마다 묻던 것을 바뀔 때만 묻는 것으로 바꾼다.

    `token` 은 알림에 `X-Goog-Channel-Token` 으로 되돌아온다. 콜백이 인증 없이
    열려 있으므로(Google 이 부른다) **이것이 유일한 신원 증명이다.**

    채널 id 는 우리가 만든다. 알림은 이 값 하나만 들고 오므로, 어느 연결의
    것인지 되찾을 수 있게 DB 에 저장해 둬야 한다.
    """

    credential = credential_for(account_id=account_id, connector_type=GOOGLE_DRIVE)
    channel_id = str(uuid4())
    expires_at = datetime.now(UTC) + DRIVE_CHANNEL_TTL
    try:
        response = requests.post(
            f"{DRIVE_CHANGES_ENDPOINT}/watch",
            headers={"Authorization": f"Bearer {credential['access_token']}"},
            params={"pageToken": page_token},
            json={
                "id": channel_id,
                "type": "web_hook",
                "address": callback_url,
                "token": token,
                # Google 은 밀리초 유닉스 타임스탬프를 문자열로 받는다.
                "expiration": str(int(expires_at.timestamp() * 1000)),
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise OAuthError("Google Drive 변경 알림 채널을 열지 못했습니다.") from exc

    resource_id = payload.get("resourceId")
    if not isinstance(resource_id, str) or not resource_id:
        # resourceId 가 없으면 **채널을 멈출 방법이 없다.** 열린 채로 두면
        # 만료까지 알림이 계속 오는데 우리는 그것이 무엇인지 모른다.
        raise OAuthError("Google Drive가 채널 식별자를 주지 않았습니다.")

    # 만료 시각은 Google 이 조정할 수 있다. 우리가 계산한 값이 아니라 **저쪽이
    # 답한 값**을 쓴다 — 갱신 판단이 실제와 어긋나면 안 된다.
    granted = payload.get("expiration")
    if granted:
        try:
            expires_at = datetime.fromtimestamp(int(granted) / 1000, tz=UTC)
        except (TypeError, ValueError):
            pass

    return {"channel_id": channel_id, "resource_id": resource_id, "expires_at": expires_at}


def stop_drive_channel(*, account_id: str, channel_id: str, resource_id: str) -> None:
    """열어 둔 채널을 멈춘다. **실패해도 올리지 않는다.**

    부르는 자리가 「연결을 끊는다」·「새 채널로 갈아탄다」라, 여기서 예외를 올리면
    정작 해야 할 일이 막힌다. 못 멈춘 채널은 만료되면 스스로 사라지고, 그때까지
    오는 알림은 우리가 모르는 채널 id 라 콜백이 조용히 버린다.
    """

    try:
        credential = credential_for(account_id=account_id, connector_type=GOOGLE_DRIVE)
        requests.post(
            "https://www.googleapis.com/drive/v3/channels/stop",
            headers={"Authorization": f"Bearer {credential['access_token']}"},
            json={"id": channel_id, "resourceId": resource_id},
            timeout=15,
        )
    except Exception:  # noqa: BLE001 — 멈추기 실패가 부르는 쪽을 막으면 안 된다
        logger.warning("Drive 채널을 멈추지 못했습니다: channel=%s", channel_id)


def list_drive_changes(*, account_id: str, page_token: str) -> tuple[list[dict[str, Any]], str]:
    """`page_token` **이후의 변경**과, 다음에 쓸 커서.

    폴더를 훑는 것과 근본이 다르다 — 폴더 스캔은 매번 전체 목록을 받아 우리 DB 와
    대조해야 하고 폴더마다 API 를 2번 부른다(상한 200폴더). 이쪽은 **바뀐 것만**
    오고, 아무것도 안 바뀌었으면 호출 1번이다. 그래서 자주 물어도 된다.

    **범위가 폴더가 아니라 계정 전체다.** 이 계정이 볼 수 있는 Drive 의 모든
    변경이 온다 — 우리 폴더 것만 고르는 것은 부르는 쪽 몫이다.

    돌려주는 커서는 두 갈래다. 끝까지 따라갔으면 `newStartPageToken`(다음번엔
    여기부터), 페이지 상한에 걸려 멈췄으면 `nextPageToken`(남은 지점). 어느
    쪽이든 그대로 저장하면 다음 회차가 이어받는다.

    `includeRemoved=true` 로 **지워진 것도 받는다.** 그게 이 API 를 쓰는 이유의
    절반이다 — 폴더 스캔은 「목록에 없다」만 알 수 있어서 휴지통·완전삭제·폴더
    밖 이동을 구별하지 못했다.
    """

    credential = credential_for(account_id=account_id, connector_type=GOOGLE_DRIVE)
    headers = {"Authorization": f"Bearer {credential['access_token']}"}
    changes: list[dict[str, Any]] = []
    cursor = page_token

    for _ in range(_DRIVE_CHANGE_MAX_PAGES):
        try:
            response = requests.get(
                DRIVE_CHANGES_ENDPOINT,
                headers=headers,
                params={
                    "pageToken": cursor,
                    "pageSize": _DRIVE_PAGE_SIZE,
                    "includeRemoved": "true",
                    "fields": (
                        "nextPageToken,newStartPageToken,"
                        "changes(fileId,removed,file(id,name,mimeType,modifiedTime,trashed))"
                    ),
                },
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise OAuthError("Google Drive 변경 목록을 받지 못했습니다.") from exc

        page = payload.get("changes")
        if not isinstance(page, list):
            raise OAuthError("Google Drive가 예상한 형식으로 응답하지 않았습니다.")
        for change in page:
            if not isinstance(change, dict) or not isinstance(change.get("fileId"), str):
                continue
            file = change.get("file") or {}
            changes.append(
                {
                    "file_id": change["fileId"],
                    # 완전히 지워졌거나 접근 권한이 사라진 경우.
                    "removed": bool(change.get("removed")),
                    # 휴지통은 되돌릴 수 있어 완전삭제와 뜻이 다르다. 다만 우리
                    # 쪽 처리는 같다 — 둘 다 「이 문서를 쓰지 않겠다」는 의도다.
                    "trashed": bool(file.get("trashed")),
                    "name": file.get("name"),
                    "mime_type": file.get("mimeType"),
                    "modified_at": file.get("modifiedTime"),
                }
            )

        next_token = payload.get("nextPageToken")
        if isinstance(next_token, str) and next_token:
            cursor = next_token
            continue

        new_start = payload.get("newStartPageToken")
        if not isinstance(new_start, str) or not new_start:
            raise OAuthError("Google Drive가 다음 변경 지점을 주지 않았습니다.")
        return changes, new_start

    # 상한에 걸렸다. 남은 지점을 커서로 돌려주면 다음 회차가 이어받는다.
    return changes, cursor


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
        # 업무 목록이 키만 늘어놓지 않도록. 없으면 화면이 키로 대신한다.
        "summary": fields.get("summary"),
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
    """프로젝트의 이슈. 제목·담당자·상태·마감·공수만 추린다.

    **완료된 것도 가져온다.** 부하 계산에는 미완료만 쓰지만(계산기가
    `status_category == 'DONE'`을 건너뛴다), 진행률은 "전체 중 얼마나 끝났나"라
    완료분이 분자·분모 양쪽에 필요하다. 미완료만 모으면 끝난 일이 통계에서
    사라져 진행률이 실제보다 낮게 나온다.

    실제 프로젝트에서는 완료 이슈가 계속 쌓이므로 언젠가 기간 제한이 필요하다.
    지금 목업은 37건이라 문제되지 않는다.
    """

    credential = credential_for(account_id=account_id, connector_type=JIRA)
    cloud_id = credential.get("cloud_id")
    if not isinstance(cloud_id, str):
        raise OAuthError("연결된 Jira 사이트 정보를 찾을 수 없습니다. 다시 연결해 주세요.")

    headers = {
        "Authorization": f"Bearer {credential['access_token']}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "jql": f'project = "{project_key}" ORDER BY key',
        "fields": ["summary", "assignee", "status", "priority", "duedate", "timetracking"],
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


#: 이슈 하나에 반드시 있어야 하는 값. 없으면 Jira 에 보내기 전에 걸러 사유를
#: 만든다(11_MCP_설계 §5 — Figma 실패 사유와 일치: issuetype·assignee 누락).
#: 보내고 나서 받는 오류는 원문이 영어이고 어느 이슈 것인지 짚기도 어렵다.
_JIRA_REQUIRED = ("title", "issuetype")

#: 한 번에 보낼 상한. Jira 벌크 API 가 50건까지 받는다.
_JIRA_BULK_LIMIT = 50


def _adf(text: str) -> dict[str, Any]:
    """평문을 Atlassian Document Format 으로.

    REST v3 의 description 은 문자열을 받지 않는다. 문자열을 그대로 보내면
    400 이 나는데 메시지가 "Operation value must be an Atlassian Document"라
    무엇이 문제인지 바로 안 보인다.
    """

    lines = [line for line in (text or "").split("\n")]
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": ([{"type": "text", "text": line}] if line else [])}
            for line in lines
        ],
    }


def create_jira_issues(
    *, account_id: str, project_key: str, issues: list[dict[str, Any]]
) -> dict[str, Any]:
    """이슈를 한 번에 만든다. **부분 실패를 그대로 돌려준다**(11_MCP_설계 §5).

    성공분만 돌려주고 나머지를 삼키면 화면이 "20건 등록"이라고 말하는데 실제로는
    17건인 상태가 된다. 건별로 성공(key)이나 실패 사유를 붙여 돌려주고, 무엇을
    다시 시도할지는 사람이 정한다.

    입력 검증을 먼저 한다. 필수 값이 빠진 건은 Jira 에 보내지 않고 여기서
    `validation` 으로 떨어뜨린다 — 보내 봐야 영어 오류가 오고, 그 오류가 어느
    이슈 것인지 되짚기 어렵다.
    """

    if not issues:
        return {"created": [], "failed": [], "project_key": project_key}
    if len(issues) > _JIRA_BULK_LIMIT:
        raise OAuthError(f"한 번에 만들 수 있는 이슈는 {_JIRA_BULK_LIMIT}건까지입니다.")

    valid: list[tuple[int, dict[str, Any]]] = []
    failed: list[dict[str, Any]] = []
    for index, issue in enumerate(issues):
        missing = [field for field in _JIRA_REQUIRED if not str(issue.get(field) or "").strip()]
        if missing:
            failed.append(
                {
                    "index": index,
                    "title": issue.get("title"),
                    "error_code": "validation",
                    "reason": f"필수 값이 없습니다: {', '.join(missing)}",
                }
            )
            continue
        valid.append((index, issue))

    if not valid:
        return {"created": [], "failed": failed, "project_key": project_key}

    credential = credential_for(account_id=account_id, connector_type=JIRA)
    cloud_id = credential.get("cloud_id")
    if not isinstance(cloud_id, str):
        raise OAuthError("연결된 Jira 사이트 정보를 찾을 수 없습니다. 다시 연결해 주세요.")

    headers = {
        "Authorization": f"Bearer {credential['access_token']}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    updates = []
    for _index, issue in valid:
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "summary": str(issue["title"])[:255],
            "issuetype": {"name": issue["issuetype"]},
        }
        if issue.get("description"):
            fields["description"] = _adf(str(issue["description"]))
        if issue.get("assignee_account_id"):
            # 이메일이 아니라 Atlassian accountId 다. GDPR 이후 이메일로는
            # 담당자를 지정할 수 없다.
            fields["assignee"] = {"accountId": issue["assignee_account_id"]}
        if issue.get("duedate"):
            fields["duedate"] = issue["duedate"]
        updates.append({"fields": fields})

    try:
        response = requests.post(
            f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/issue/bulk",
            headers=headers,
            json={"issueUpdates": updates},
            timeout=(10, 60),
        )
    except requests.RequestException as exc:
        raise OAuthError(f"Jira 이슈 생성 요청에 실패했습니다: {exc}") from exc

    if response.status_code in (401, 403):
        raise OAuthError("Jira 인증이 만료되었습니다. 설정에서 다시 연결해 주세요.")
    if response.status_code == 429:
        raise OAuthError("Jira 요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.")
    if response.status_code >= 400 and response.status_code != 400:
        # 400 은 "일부 실패"일 수 있어 본문을 읽어야 한다. 그 외는 전체 실패다.
        raise OAuthError(f"Jira 이슈 생성에 실패했습니다: HTTP {response.status_code}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise OAuthError("Jira 응답을 읽을 수 없습니다.") from exc

    created = [
        {"key": item.get("key"), "id": item.get("id")} for item in payload.get("issues") or []
    ]
    # `failedElementNumber` 는 우리가 보낸 배열의 인덱스다 — 걸러낸 건이 있으므로
    # 원래 요청 순번으로 되돌려 준다. 안 그러면 화면이 엉뚱한 업무에 사유를 붙인다.
    for error in payload.get("errors") or []:
        position = error.get("failedElementNumber")
        original_index, issue = (
            valid[position] if isinstance(position, int) and position < len(valid) else (None, {})
        )
        status_payload = error.get("elementErrors") or {}
        messages = status_payload.get("errorMessages") or []
        field_errors = status_payload.get("errors") or {}
        failed.append(
            {
                "index": original_index,
                "title": issue.get("title"),
                "error_code": "validation",
                "reason": "; ".join([*messages, *(f"{k}: {v}" for k, v in field_errors.items())])
                or "Jira 가 이 이슈를 거부했습니다.",
            }
        )

    return {
        "project_key": project_key,
        "created": created,
        "failed": sorted(failed, key=lambda row: (row["index"] is None, row["index"])),
    }


def find_jira_account_id_by_email(*, account_id: str, email: str) -> str | None:
    """이메일로 Jira accountId 를 찾는다. **못 찾으면(0건·다건) 예외 대신 None.**

    담당자를 지정하지 않은 이슈에 요청자 자신을 기본값으로 채우려는 보조
    조회다(2026-08-20, `_jira_create_issues` 에서 씀) — 이 조회가 "못 찾았다"로
    끝난다고 이슈 생성 자체를 막을 이유는 없다. 우리 팀이 이미 문서로 정해 둔
    원칙과 같다: "막히면 담당자를 이슈 본문에 적고 assignee는 비운다"
    (`docs/설계 및 구현/3_중간발표 이후/설계/5_E2E_시나리오.md`). Jira 계정 설정에 따라 이메일이 검색에
    안 걸릴 수 있고(0건), 동명이인·중복 계정으로 여러 건일 수도 있다(다건) —
    두 경우 다 **확신 없이 배정하지 않는다**: 정확히 한 건일 때만 accountId 를
    돌려준다.

    **자격증명 문제(`OAuthError`)는 예외다 — 여기서 삼키지 않고 그대로
    올린다**(2026-08-20 수정). 이 조회와 뒤이은 `create_jira_issues()` 호출은
    **같은 `account_id`, 같은 커넥터**로 자격증명을 다시 조회한다
    (`credential_for()`). 여기서 만료·재연결 필요로 실패했다면 뒤의 호출도
    똑같은 이유로 반드시 실패한다 — `credential_for()`가 갱신 실패 시
    `ConnectorRepository.mark_expired()`까지 이미 남겨 상태가 확정된
    뒤이기도 하다. 여기서 삼키고 다음 호출까지 마저 보내면, 이미 결과를 아는
    Jira 요청을 한 번 더 보내는 것뿐이다(불필요한 API 호출 1회 + 그 결과를
    기다리는 모델 턴 낭비) — `_jira_create_issues()`가 이 예외를 받아 그
    자리에서 바로 실패하게 둔다(§ `_fill_default_jira_assignee` 참고).
    네트워크 오류·이상 응답(`requests.RequestException`, `ValueError`)은
    이 호출 하나만의 문제일 수 있어 계속 "못 찾았다"로 접는다 — 자격증명과
    달리 다음 호출이 반드시 같은 이유로 실패한다는 보장이 없다.

    `account_id` 는 **자격증명 조회용**이다 — Jira는 팀장만 연결하므로 호출하는
    쪽에서 팀장 account_id 를 넘겨야 한다(`_jira_credential_account_id`,
    `services/harness/registry.py`). 검색 대상은 `email` 이지 `account_id` 가
    아니다 — 이 함수만으로는 "누구를 찾을지"와 "누구 자격증명으로 찾을지"가
    다른 사람일 수 있다.

    `read:jira-user` 스코프는 이미 우리 OAuth 연결에 포함돼 있다
    (`apps/connectors/oauth.py` 의 `JIRA_SCOPES`) — 별도 재동의가 필요 없다.
    """

    credential = credential_for(account_id=account_id, connector_type=JIRA)
    cloud_id = credential.get("cloud_id")
    if not isinstance(cloud_id, str):
        # `create_jira_issues()`가 같은 조건에서 내는 것과 같은 메시지 —
        # 여기서 먼저 막히든 거기서 막히든 사용자가 보는 이유는 같아야 한다.
        raise OAuthError("연결된 Jira 사이트 정보를 찾을 수 없습니다. 다시 연결해 주세요.")

    try:
        response = requests.get(
            f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/user/search",
            headers={
                "Authorization": f"Bearer {credential['access_token']}",
                "Accept": "application/json",
            },
            params={"query": email},
            timeout=15,
        )
        response.raise_for_status()
        matches = response.json()
    except (requests.RequestException, ValueError):
        # 네트워크가 죽었든 응답이 이상하든 — "못 찾았다"로 접는다. 이건 이슈
        # 생성의 부수 조회지 필수 조건이 아니고, 자격증명과 달리 다음 호출도
        # 똑같이 실패한다는 보장이 없다(위 docstring).
        return None

    if not isinstance(matches, list):
        return None
    account_ids = {
        item["accountId"]
        for item in matches
        if isinstance(item, dict) and isinstance(item.get("accountId"), str)
    }
    if len(account_ids) != 1:
        return None
    return next(iter(account_ids))
