"""연결된 저장소의 파일을 **본문 색인까지** 받아들인다.

한 건이 이상하다고 나머지를 멈추지 않는다. 팀 문서 전부에 도는 일이라 한 건의
실패는 그 한 건으로 끝나야 한다 — 옛 API 뷰들이 지키던 규칙을 그대로 가져온다.

**단, 커넥터 자격증명 자체가 막힌 경우(`OAuthError`)는 예외다**(2026-08-20).
파일 한 건의 문제(깨진 파일, 저장소 오류)와 달리, 자격증명 문제는 같은
계정·같은 커넥터로 도는 남은 모든 건에 반드시 똑같이 재현된다 — "이 건만
실패로 끝난다"는 원칙이 여기엔 적용되지 않는다. `_fetch_originals()`가
이 경우 나머지 대기 문서를 더 시도하지 않고 배치를 멈춘다. `_index_all()` 의
`PipelineConfigurationError` 도 같은 이유로 배치를 멈춘다.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from apps.connectors.clients import (
    download_drive_file,
    drive_start_page_token,
    list_drive_changes,
    list_drive_files,
)
from apps.connectors.oauth import OAuthError
from backend.db import (
    AccountRepository,
    ConnectorRepository,
    DocumentRepository,
    TeamFolderRepository,
)
from backend.db.document_pipeline import PipelineDocumentRepository
from backend.db.errors import RepositoryError
from backend.services.storage import build_key, content_hash
from backend.services.storage import remove as remove_document
from backend.services.storage import save as save_document
from services.document_pipeline.errors import DocumentPipelineError, PipelineConfigurationError
from services.document_intake.public_errors import safe_document_failure_detail

logger = logging.getLogger(__name__)


@dataclass
class IntakeResult:
    """무엇이 새로 들어왔고 무엇이 안 됐는가.

    **숫자만 돌려주지 않는다.** 안 된 것은 이유와 함께 남겨야 「연결은 됐는데
    문서가 없다」를 사람에게 설명할 수 있다.
    """

    registered: list[str] = field(default_factory=list)
    #: Drive 에서 고쳐져 다시 받은 문서(2026-08-24). 등록과 나눠 센다 —
    #: 「새로 들어온 것」과 「내용이 바뀐 것」은 사람이 확인할 것이 다르다.
    refreshed: list[str] = field(default_factory=list)
    #: 본문 청크·임베딩까지 올라간 문서. 등록(`registered`)과 나눠 센다 —
    #: 등록만 된 문서는 목록에 보이지만 **문장 근거를 내지 못한다.**
    indexed: list[str] = field(default_factory=list)
    failed: list[dict[str, str]] = field(default_factory=list)
    #: Drive 에서 지워져 우리도 내린 문서(2026-08-24). 폴더 스캔으로는 「목록에
    #: 없다」까지만 알 수 있어 사람 확인이 필요했는데, Changes API 가 휴지통·
    #: 완전삭제를 명시해 주면서 자동으로 처리할 수 있게 됐다.
    removed: list[str] = field(default_factory=list)
    #: 저장소를 아예 못 읽은 경우. 이때는 위 넷이 모두 비어 있어도 「문서가
    #: 없다」는 뜻이 아니다.
    storage_error: str | None = None


def intake_connector_documents(*, account_id: str, limit: int = 20) -> IntakeResult:
    """연결된 폴더의 파일을 `doc` 에 넣고 내려받아 **본문 색인까지** 만든다.

    `limit` 은 한 번에 새로 **등록**하는 문서 수다. 폴더가 크면 첫 호출이 통째로
    길어지므로 나눠 받고, 나머지는 다음 호출이 이어받는다.

    색인(`_index_all`)에는 `limit` 이 걸리지 않는다. 등록이 회차당 `limit` 건으로
    묶여 있으므로 색인 대기도 자연히 그 언저리이고, 앞 회차에서 못 끝낸 것을
    여기서 마저 집어야 폴더가 결국 전부 색인된다.

    **이미 있는 것은 건드리지 않는다.** 등록된 파일은 건너뛰고, 청크가 있는
    문서는 다시 색인하지 않는다. 여러 번 불러도 안전해야 저장소가 바뀔 때마다
    부담 없이 부를 수 있다.
    """

    result = IntakeResult()

    folders = TeamFolderRepository.list_for_team(account_id)
    if not folders:
        return result

    team_id = AccountRepository.team_id(account_id)
    if team_id is None:
        return result

    try:
        known = DocumentRepository.registered_file_ids(account_id)
        candidates: list[dict[str, Any]] = []
        # 훑으면서 본 **모든** 파일의 수정 시각. 변경 감지가 이 값을 쓴다
        # (2026-08-24) — 스캔은 어차피 도니 Drive 호출이 늘지 않는다.
        live_modified: dict[str, str | None] = {}
        for folder in folders:
            for item in list_drive_files(
                account_id=account_id,
                parent_id=folder["external_folder_id"],
                # **`None` 은 「제한 없음」이다.** `or 1` 로 접으면 사람이 화면에서
                # 고른 「제한 없음」이 조용히 「선택한 폴더만」이 된다 — 폴더 고르는
                # 화면은 `depth=unlimited` 로 물어 파일을 보여 주는데 수집은 0건이라,
                # 어디가 틀렸는지 보이지 않는다(2026-08-28 실서버에서 실제로 겪었다).
                max_depth=folder.get("max_depth"),
            ):
                live_modified[item["file_id"]] = item["modified_at"]
                # 파싱할 수 없는 형식은 받아들이지 않는다. 목록에는 보여 주되
                # (`document_list`) 저장소에 넣어 봐야 읽을 수 없다.
                if not item["supported"] or item["file_id"] in known:
                    continue
                # `limit` 은 **새로 등록하는 수**만 묶는다. 폴더 순회를 여기서
                # 끊으면 뒤쪽 폴더의 수정 시각을 못 보고, 첫 폴더가 매번 한도를
                # 채우면 그 뒤 폴더의 변경은 영영 감지되지 않는다(2026-08-24).
                if len(candidates) < limit:
                    # **어느 폴더를 훑던 중인지는 여기서만 안다**(2026-08-25).
                    # `list_drive_files` 는 뿌리 안에서의 상대 경로만 붙여 주고
                    # 그 뿌리가 어느 `team_folder` 인지는 이 반복문이 들고 있다.
                    # 「문서」 화면의 폴더 트리가 이 둘로 그려진다.
                    candidates.append({**item, "team_folder_id": folder["team_folder_id"]})
    except Exception as exc:  # noqa: BLE001 — 저장소 사정이 이 함수를 죽이지 않는다
        logger.exception("연결된 저장소 목록을 읽지 못했다")
        result.storage_error = exc.__class__.__name__
        return result

    if candidates:
        try:
            created = DocumentRepository.add_drive_documents(
                account_id=account_id,
                documents=[
                    {
                        "src_file_id": item["file_id"],
                        "file_name": item["name"],
                        "mime_type": item["mime_type"],
                        # 등록 시점에는 이 문서가 어느 프로젝트의 무엇인지 모른다.
                        # `doc_role` 은 기준 문서로 뽑힐 때 채워진다.
                        "doc_role": None,
                        "src_modified_at": item["modified_at"],
                        # 뿌리 폴더와 그 안에서의 상대 경로. `folder_path` 는
                        # 뿌리 바로 아래면 빈 문자열이라 **NULL 과 뜻이 다르다** —
                        # NULL 은 이 칸이 생기기 전에 등록된 문서다.
                        "team_folder_id": item["team_folder_id"],
                        "src_folder_path": item["folder_path"],
                    }
                    for item in candidates
                ],
            )
        except (RepositoryError, Exception) as exc:  # noqa: BLE001
            logger.exception("문서 등록 실패")
            result.storage_error = exc.__class__.__name__
            return result
        result.registered = [row["file_name"] for row in created]

    _fetch_originals(account_id=account_id, team_id=team_id, result=result)
    _refetch_changed(
        account_id=account_id, team_id=team_id, live_modified=live_modified, result=result
    )
    # 재수신이 `cur_revision` 을 바꾸면 옛 청크가 `b.revision = d.cur_revision` 에
    # 걸려 빠지고, 그 문서가 다시 색인 대기로 잡힌다 — 그래서 이 순서다.
    _index_all(account_id=account_id, team_id=team_id, result=result)
    return result


def sync_drive_changes(*, account_id: str) -> IntakeResult:
    """Drive 의 **변경분만** 따라가 반영한다. 대화를 시작할 때 돈다.

    폴더 스캔과 근본이 다르다. 스캔은 매번 전체 목록을 받아 우리 DB 와 대조해야
    하고 폴더마다 API 를 2번 부른다(상한 200폴더) — 비싸서 자주 못 돌리고, 그래서
    「폴더 설정을 저장할 때」만 돌고 있었다. Changes API 는 지난 지점 이후의 것만
    주고 변화가 없으면 호출 1번이라, **대화마다 물어도 부담이 없다.**

    `account_id` 는 **대화를 시작한 사람**이다. 자격증명 주인은 다를 수 있다 —
    커넥터를 연결하는 것은 팀장뿐인데 대화는 팀원 누구나 시작한다. 그래서
    `drive_sync_target` 이 `team_folder` 를 거쳐 이 팀의 연결과 그 소유 계정을
    찾아 주고, 아래 호출은 전부 **그 계정**으로 한다.

    **커서가 없으면 기준점만 잡고 끝낸다.** 연결 이전의 변경까지 거슬러 올라갈
    이유가 없다 — 처음 등록은 폴더 스캔이 이미 했다.

    삭제는 **사람에게 묻지 않고 바로 내린다**(2026-08-24). 폴더 스캔 시절에는
    휴지통·완전삭제·폴더 밖 이동이 전부 「목록에 없다」로 보여 구별이 안 됐고,
    그래서 사람 확인을 뒀다(`list_missing_from_drive`). Changes API 는 `removed`
    와 `trashed` 를 명시하므로 그 모호함이 사라진다. 잘못 내려도 원본은 Drive 에
    있고 `restore_reappeared` 가 되살린다 — 반대로 안 내리면 사용자가 지운 문서의
    **본문 전체**가 우리 검색에 계속 남는다.

    **이 함수는 실패해도 조용히 끝난다.** 대화를 시작하려는 사람이 문서 동기화
    때문에 막히면 안 된다.
    """

    result = IntakeResult()

    target = ConnectorRepository.drive_sync_target(account_id)
    if target is None:
        # 연결이 없거나 읽을 폴더가 없다. 따라갈 변경도 없다.
        return result

    owner = target["account_id"]
    conn_id = target["conn_id"]

    try:
        if not target["sync_cursor"]:
            ConnectorRepository.set_sync_cursor(
                conn_id=conn_id, cursor_value=drive_start_page_token(account_id=owner)
            )
            return result

        changes, next_cursor = list_drive_changes(
            account_id=owner, page_token=target["sync_cursor"]
        )
    except (OAuthError, RepositoryError) as exc:
        logger.warning("Drive 변경 동기화 실패: account=%s (%s)", account_id, exc)
        result.storage_error = exc.__class__.__name__
        return result

    team_id = AccountRepository.team_id(owner)
    if team_id is None:
        return result

    gone = [row["file_id"] for row in changes if row["removed"] or row["trashed"]]
    touched = {
        row["file_id"]: row["modified_at"]
        for row in changes
        if not (row["removed"] or row["trashed"]) and row["modified_at"]
    }

    try:
        doc_ids = DocumentRepository.doc_ids_for_source(account_id=owner, file_ids=gone)
        if doc_ids:
            DocumentRepository.mark_removed_from_drive(account_id=owner, doc_ids=doc_ids)
            result.removed = doc_ids
    except (RepositoryError, Exception) as exc:  # noqa: BLE001
        logger.exception("사라진 문서 정리 실패: account=%s", account_id)
        result.failed.append({"file_name": "(삭제 반영)", "detail": exc.__class__.__name__})

    if touched:
        _refetch_changed(
            account_id=owner, team_id=team_id, live_modified=touched, result=result
        )
        # 재수신이 `cur_revision` 을 바꾼 문서는 색인 대기로 돌아온다.
        _index_all(account_id=owner, team_id=team_id, result=result)

    # **커서는 마지막에 옮긴다.** 먼저 저장하면 처리 중에 죽었을 때 그 구간을
    # 영영 다시 못 본다. 같은 변경을 두 번 보는 쪽이 낫다 — 재수신은
    # `content_hash` 가 같으면 아무것도 하지 않는다.
    try:
        ConnectorRepository.set_sync_cursor(conn_id=conn_id, cursor_value=next_cursor)
    except (RepositoryError, Exception) as exc:  # noqa: BLE001
        logger.exception("동기화 커서 저장 실패: account=%s", account_id)
        result.failed.append({"file_name": "(커서 저장)", "detail": exc.__class__.__name__})

    return result


def _refetch_changed(
    *,
    account_id: str,
    team_id: str,
    live_modified: dict[str, str | None],
    result: IntakeResult,
) -> None:
    """Drive 에서 고쳐진 문서를 다시 받는다.

    **없으면 우리는 영원히 옛 판으로 답한다.** 기획서를 개정해도 요약·본문·업무
    추출 근거가 전부 등록 시점 그대로였다 — 화면 어디에도 낡았다는 표시가 없어
    틀린 답이 맞는 답처럼 나갔다(2026-08-24 이전).

    **두 단으로 거른다.**

    1. `modifiedTime` 이 우리 기록보다 최신인 것만 후보로(`list_changed_on_drive`)
    2. 그 후보만 내려받아 `content_hash` 를 대조 — 같으면 시각만 갱신하고 끝

    `modifiedTime` 은 이름 변경·공유 설정 변경·이동에도 오른다. 1단만 믿고
    재파싱하면 내용이 그대로인 문서로 GPU 를 태운다. 2단의 다운로드는 파싱보다
    훨씬 싸다 — `content_hash` 를 저장해 둔 이유가 이것이다.

    내용이 정말 바뀌었으면 **같은 `storage_key` 에 덮어쓴다.** 옛 판을 남길
    이유가 없다(원본은 Drive 에 있고, 우리는 사본이다). `mark_stored` 가
    `cur_revision` 을 바꾸는 순간 옛 청크는 검색에서 빠지고 재색인 대기로
    잡힌다 — 재색인을 여기서 시키지 않는 이유다.

    사라진 문서와 다르게 **사람에게 묻지 않는다.** 없어진 것은 휴지통·완전삭제·
    폴더 밖 이동이 구별되지 않아 확인이 필요하지만, 바뀐 것은 의도가 분명하고
    되돌릴 것도 없다 — 「지울까요」가 아니라 「새 판을 읽는다」다.
    """

    try:
        targets = DocumentRepository.list_changed_on_drive(
            account_id=account_id, live_modified=live_modified
        )
    except (RepositoryError, Exception) as exc:  # noqa: BLE001
        logger.exception("변경 감지 실패: account=%s", account_id)
        result.failed.append({"file_name": "(변경 감지)", "detail": exc.__class__.__name__})
        return

    for index, target in enumerate(targets):
        try:
            fetched = download_drive_file(
                account_id=account_id,
                file_id=target["src_file_id"],
                mime_type=target["mime_type"],
            )
        except OAuthError as exc:
            # 자격증명이 막혔다는 뜻이라 남은 문서도 전부 같은 이유로 실패한다
            # (`_fetch_originals` 와 같은 규칙).
            logger.exception("변경분 수신 실패(자격증명): %s", target["doc_id"])
            for remaining in targets[index:]:
                result.failed.append(
                    {"file_name": remaining["file_name"], "detail": exc.__class__.__name__}
                )
            break
        except (OSError, RepositoryError) as exc:
            logger.exception("변경분 수신 실패: %s", target["doc_id"])
            result.failed.append(
                {"file_name": target["file_name"], "detail": exc.__class__.__name__}
            )
            continue

        try:
            key = build_key(
                team_id=team_id, doc_id=target["doc_id"], mime_type=fetched["mime_type"]
            )
            fetched_hash = content_hash(fetched["content"])
            if fetched_hash == target["content_hash"]:
                # 내용은 그대로다. 시각만 맞춰 두지 않으면 다음 스캔이 같은
                # 문서를 또 후보로 올려 매번 내려받게 된다.
                DocumentRepository.mark_unchanged(
                    doc_id=target["doc_id"],
                    src_modified_at=target["drive_modified_at"],
                )
                continue

            save_document(key, fetched["content"])
            DocumentRepository.mark_stored(
                doc_id=target["doc_id"],
                storage_key=key,
                content_hash=fetched_hash,
                revision=fetched["revision"],
                src_modified_at=target["drive_modified_at"],
            )
        except (OSError, RepositoryError) as exc:
            logger.exception("변경분 저장 실패: %s", target["doc_id"])
            result.failed.append(
                {"file_name": target["file_name"], "detail": exc.__class__.__name__}
            )
            continue

        result.refreshed.append(target["file_name"])


def _index_all(*, account_id: str, team_id: str, result: IntakeResult) -> None:
    """받아들인 문서를 **전부** 본문 색인까지 올린다.

    전에는 요약까지만 하고, 청크 파싱·임베딩은 대화 중 요약으로 좁혀진 문서에만
    돌렸다(2026-08-15 PM). 그 판단을 뒤집는다 — 플랫폼이 「연결된 폴더의 문서를
    검색한다」고 말하는 이상 **권한 범위 안의 문서는 결국 전부 색인되어 있어야**
    한다. 요약 단계는 그래서 통째로 없앴다(2026-08-24).

    한 번에 다 끝내지 않아도 된다. 워커 슬롯이 하나라 순차로 돌고, 못 끝낸
    문서는 다음 호출이 이어받는다(`list_pending_index` 가 남은 것만 준다).
    부르는 쪽이 이미 응답을 붙잡지 않는 뒷작업이라 여기서 오래 걸려도 화면은
    기다리지 않는다.

    **한 건의 실패가 나머지를 멈추지 않는다** — 이 모듈의 규칙 그대로다. 다만
    RunPod 설정 자체가 없으면(`PipelineConfigurationError`) 남은 문서도 전부
    같은 이유로 실패하므로 거기서 멈춘다. 자격증명 실패를 다루는 방식과 같다.
    """

    pending = PipelineDocumentRepository.list_pending_index(team_id)
    for index, doc_id in enumerate(pending):
        try:
            outcome = promote_to_searchable(account_id=account_id, doc_id=doc_id)
        except PipelineConfigurationError as exc:
            logger.exception("본문 색인 불가(설정 없음): %s", doc_id)
            for remaining in pending[index:]:
                result.failed.append(
                    {"file_name": remaining, "detail": exc.__class__.__name__}
                )
            break
        except (ValueError, OSError, RepositoryError, DocumentPipelineError) as exc:
            logger.exception("본문 색인 실패: %s", doc_id)
            result.failed.append({"file_name": doc_id, "detail": exc.__class__.__name__})
            continue

        if outcome["ok"]:
            result.indexed.append(doc_id)
        else:
            # 240초 안에 못 끝낸 것도 여기로 온다. 실패와 구분되는 상태지만
            # 「이번 회차에 안 끝났다」는 점은 같고, 다음 호출이 다시 집는다.
            result.failed.append(
                {"file_name": doc_id, "detail": outcome.get("detail") or "색인 미완료"}
            )


def _fetch_originals(*, account_id: str, team_id: str, result: IntakeResult) -> None:
    """원문을 받아 저장소에 넣는다.

    **요약은 더 이상 만들지 않는다**(2026-08-24). 요약은 전량 색인이 없던 시절
    문서를 좁히려고 만들던 값인데, 이제 폴더의 문서가 전부 본문까지 색인되므로
    좁힐 이유가 없다 — 색인된 본문에서 직접 찾는 쪽이 요약보다 정확하다.

    여기서 원문만 확보하고 색인은 `_index_all` 이 이어받는다. 나누는 이유는
    다운로드가 실패하는 방식(자격증명·네트워크)과 색인이 실패하는 방식(워커·
    형식)이 달라서다 — 한 함수에 두면 「자격증명이 막혀 배치를 멈춘다」는 판단이
    색인 실패에도 걸린다.
    """

    # `list()`로 미리 확정해 둔다 — 아래에서 자격증명 실패 시 "남은 항목"을
    # 한 번에 훑어야 하는데, 제너레이터면 다시 훑을 수 없다.
    targets = list(DocumentRepository.list_pending_download(account_id))
    for index, target in enumerate(targets):
        if target["storage_key"]:
            continue
        try:
            fetched = download_drive_file(
                account_id=account_id,
                file_id=target["src_file_id"],
                mime_type=target["mime_type"],
            )
            key = build_key(team_id=team_id, doc_id=target["doc_id"], mime_type=fetched["mime_type"])
            # 파일을 먼저 쓰고 DB 에 기록한다. 반대 순서면 「DB 에는 있는데 파일이
            # 없는」 상태가 생기고 파싱이 그걸 읽다가 죽는다.
            content_hash = save_document(key, fetched["content"])
            DocumentRepository.mark_stored(
                doc_id=target["doc_id"],
                storage_key=key,
                content_hash=content_hash,
                revision=fetched["revision"],
            )
        except OAuthError as exc:
            # 2026-08-20 수정 — 이 계정의 이 커넥터 자격증명이 막혔다는 뜻이다.
            # `download_drive_file()`은 항목마다 같은 `account_id`로
            # `credential_for()`를 다시 부르므로, 여기서 막히면 남은 대기
            # 문서도 전부 같은 이유로 똑같이 실패한다 — 하나씩 돌며 매번 같은
            # Drive 요청을 다시 보낼 이유가 없다. 남은 항목을 같은 사유로
            # 한 번에 기록하고 이 배치는 여기서 멈춘다(다음 호출이 이어받는다
            # — 이 함수의 "여러 번 불러도 안전하다" 원칙 그대로).
            logger.exception("원문 수신 실패(자격증명): %s", target["doc_id"])
            for remaining in targets[index:]:
                if remaining["storage_key"]:
                    continue
                result.failed.append(
                    {"file_name": remaining["file_name"], "detail": exc.__class__.__name__}
                )
            break
        except (OSError, RepositoryError) as exc:
            logger.exception("원문 수신 실패: %s", target["doc_id"])
            result.failed.append({"file_name": target["file_name"], "detail": exc.__class__.__name__})


#: 청크 파싱·임베딩 한 건을 기다려 주는 한계(초).
#:
#: RunPod 워커가 모델을 이미지에 넣지 않아 첫 실행이 몇 분이다. 여기서 무한정
#: 기다리면 대화가 멈춘 것처럼 보이므로, 못 끝내면 **그 사실을 답에 담아** 넘긴다
#: — 조용히 실패하면 「관련 문서가 없다」로 읽힌다.
PROMOTE_WAIT_SECONDS = 240

#: 사람이 응답을 붙잡고 있지 **않을 때** 기다려 주는 한계(초).
#:
#: 위 240초는 대화 도구를 위한 값이다 — 그 턴 안에 답해야 하니 오래 못 기다린다.
#: 그런데 업로드·「다시 읽기」는 뒷작업이라 붙잡고 있는 것이 없는데도 같은 4분에
#: 포기했고, **그러면 그 문서는 영영 색인되지 않는다**: 시간이 다 되면 `_done` 을
#: 안 부르고 나가므로 워커가 마친 결과를 아무도 적재하지 않고, 다시 눌러도 같은
#: 4분을 다시 쓴다. 쪽수가 많은 문서(예: 200쪽 설계서)가 여기 걸린다.
#:
#: **RunPod 쪽은 원래 30분까지 허용해 두었다**(`RUNPOD_EXECUTION_TIMEOUT_MS`,
#: 운영 `.env` 에서 1,800,000ms). 기다리는 쪽만 4분이라 그 여유를 못 쓰고 있었다.
#: 그 아래로 잡아 워커가 끝낼 시간을 남긴다.
LONG_PROMOTE_WAIT_SECONDS = 1_500


def _worker_failure_detail(result: dict[str, Any], state: str) -> str:
    """워커가 왜 실패했는지를 화면에 쓸 한 줄로 만든다.

    RunPod 의 `error` 는 워커가 만든 **JSON 문자열**이다 — `error_type`,
    `error_message`, `error_traceback` 이 들어 있다. 상태값만 적으면 화면에
    「문서 처리 실패(FAILED)」가 뜨는데, 그건 `index_detail` 을 만든 이유를
    지우는 것이다(2026-08-24). 실제로 그 자리에 들어가야 할 말은 예를 들어
    「표 #/tables/14의 셀 구조가 비어 있습니다」다.

    트레이스백은 넣지 않는다. 사람이 읽는 칸이고, 스택은 워커 로그에 있다.
    """

    raw = result.get("error")
    if isinstance(raw, str) and raw.strip():
        error_type = ""
        try:
            parsed = json.loads(raw)
            message = parsed.get("error_message")
            error_type = str(parsed.get("error_type") or "")
        except (ValueError, AttributeError):
            message = raw
        if message:
            return safe_document_failure_detail(message, state=state, error_type=error_type)
    return safe_document_failure_detail(None, state=state)


def _refetch_original(*, account_id: str, document: dict[str, Any]) -> bool:
    """색인 뒤 버린 원문을 Drive 에서 다시 받아 온다. 받았으면 True.

    **다시 읽히려면 원문이 다시 필요하다.** 커넥터 문서는 색인이 끝나면 원문을
    버리므로(`_discard_original`), 「다시 읽기」나 재색인은 여기를 지난다.

    올린 파일에는 돌아갈 곳이 없다(`src_file_id` 가 없다) — False 로 답하고
    부르는 쪽이 사유를 적는다.
    """

    if not document.get("src_file_id") or not document.get("team_id"):
        return False

    fetched = download_drive_file(
        account_id=account_id,
        file_id=document["src_file_id"],
        mime_type=document["mime_type"],
    )
    key = build_key(
        team_id=document["team_id"], doc_id=document["doc_id"], mime_type=fetched["mime_type"]
    )
    # 파일을 먼저 쓰고 DB 에 기록한다 — `_fetch_originals` 와 같은 순서다.
    fetched_hash = save_document(key, fetched["content"])
    DocumentRepository.mark_stored(
        doc_id=document["doc_id"],
        storage_key=key,
        content_hash=fetched_hash,
        revision=fetched["revision"],
    )
    return True


def _discard_original(document: dict[str, Any]) -> None:
    """색인이 끝난 **커넥터 문서**의 원문을 버린다 (2026-08-26 결정).

    원본은 Drive 에 있고 우리는 사본이었다. 검색이 쓰는 것은 청크와 임베딩이지
    원문 파일이 아니라, 다 읽고 나면 들고 있을 이유가 없다. 다시 읽어야 할 때는
    `_refetch_original` 이 Drive 에서 받아 온다.

    **올린 파일은 안 버린다.** 그쪽은 원본이 우리뿐이라 버리면 되돌릴 곳이 없다 —
    `src_file_id` 가 그 구분이다.

    실패해도 색인 결과를 뒤집지 않는다. 파일이 남는 것은 다음 저장이 덮어쓰고,
    최악이라도 「지웠어야 할 사본이 남았다」이지 문서가 망가지는 일은 아니다.
    """

    if not document.get("src_file_id") or not document.get("storage_key"):
        return
    try:
        remove_document(document["storage_key"])
        DocumentRepository.clear_stored_original(document["doc_id"])
    except (OSError, RepositoryError):
        logger.exception("원문 정리 실패: %s", document["doc_id"])


def promote_to_searchable(
    *, account_id: str, doc_id: str, wait_seconds: float = PROMOTE_WAIT_SECONDS
) -> dict[str, Any]:
    """문서 하나를 **본문 검색 가능**한 상태로 올린다.

    요약까지만 되어 있던 문서를 청크로 쪼개 임베딩한다.

    부르는 곳이 셋이다 — 폴더를 저장한 뒤 도는 전량 색인(`_index_all`), 검색이
    좁힌 후보 중 아직 청크가 없는 문서, 그리고 기준 문서로 지정된 문서. 앞의
    것이 정상 경로이고 뒤의 둘은 **아직 전량 색인이 닿지 않은 문서를 그 자리에서
    끌어올리는** 보충 경로다(워커가 순차라 폴더가 크면 시차가 생긴다).

    끝났는지 여기서 기다린다. 부르는 쪽이 도구라 「제출했습니다」로 끝내면
    그 턴 안에서 쓸 수가 없다.

    `wait_seconds` 는 **누가 기다리느냐**로 갈린다. 기본값은 대화 도구용 4분이고,
    사람이 응답을 붙잡고 있지 않은 뒷작업(업로드·「다시 읽기」)은
    `LONG_PROMOTE_WAIT_SECONDS` 를 준다 — 그 주석에 왜인지 적어 두었다.
    """

    from django.conf import settings

    from services.document_pipeline.runpod_client import job_status, submit_document_job
    from services.document_pipeline.signing import signed_download_url

    from backend.db.document_pipeline import PersonalDocumentRepository

    document = PipelineDocumentRepository.get_for_processing(doc_id=doc_id, account_id=account_id)
    if not document["storage_key"]:
        # 색인이 끝나 버린 원문이거나, 아직 한 번도 못 받은 문서다. Drive 에서
        # 받아 올 수 있으면 받고, 아니면 여기서 끝낸다.
        try:
            recovered = _refetch_original(account_id=account_id, document=document)
        except (OAuthError, OSError, RepositoryError) as exc:
            logger.exception("원문 재수신 실패: %s", doc_id)
            return {"doc_id": doc_id, "ok": False, "detail": exc.__class__.__name__}
        if not recovered:
            return {"doc_id": doc_id, "ok": False, "detail": "원문을 아직 받지 않았습니다."}
        document = PipelineDocumentRepository.get_for_processing(
            doc_id=doc_id, account_id=account_id
        )

    # **결과를 남긴다.** 안 남기면 실패한 문서와 아직 안 돌린 문서가 화면에서
    # 같아 보인다 — 사람은 얼마나 더 기다려야 하는지 알 수 없다(2026-08-18).
    PersonalDocumentRepository.set_index_status(doc_id=doc_id, status="RUNNING")

    def _done(ok: bool, **rest):
        # 실패 사유를 그대로 칸에 넣는다 — 화면이 「왜 안 되는지」를 말할 수
        # 있어야 한다(2026-08-24, 없앤 `doc_meta.extract_detail` 의 역할).
        PersonalDocumentRepository.set_index_status(
            doc_id=doc_id,
            status=None if ok else "FAILED",
            detail=None if ok else rest.get("detail"),
        )
        return {"doc_id": doc_id, "ok": ok, **rest}

    job = submit_document_job(
        {
            "doc_id": doc_id,
            "revision": document["cur_revision"],
            "mime_type": document["mime_type"],
            "source_url": signed_download_url(doc_id=doc_id, revision=document["cur_revision"]),
            "max_tokens": settings.CHUNKING_MAX_TOKENS,
            "merge_peers": settings.CHUNKING_MERGE_PEERS,
        }
    )

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        time.sleep(3)
        result = job_status(job["id"])
        state = result.get("status")
        if state == "COMPLETED":
            output = result.get("output")
            if not isinstance(output, dict):
                return _done(False, detail="처리 결과가 비어 있습니다.")
            # 완료 시점에 바로 적재한다. RunPod 는 완료 결과를 제한된 시간만
            # 보관해서 나중에 다시 받아 오면 되겠지 하고 미룰 수 없다.
            try:
                PipelineDocumentRepository.ingest(expected_doc=document, result=output)
            except ValueError as exc:
                # **워커는 성공했는데 적재가 거절된 경우다.** `ingest` 는 결과가
                # 우리 기록과 안 맞으면 일부러 `ValueError` 를 낸다(revision 이
                # 도중에 바뀌었다, content hash 가 다르다 …). 그것이 여기를 그냥
                # 뚫고 나가면 `_done` 이 안 불려 **문서가 `RUNNING` 에 갇힌다** —
                # 화면은 영원히 「읽는 중」이고, 그건 `index_status` 를 만든 이유
                # 자체를 지우는 것이다(2026-08-18).
                #
                # 2026-08-25 에 실제로 밟았다. DC001 의 `content_hash` 가 저장된
                # 원문과 어긋나 있었고, 워커가 정상 완료한 뒤 여기서 터졌다.
                return _done(False, detail=str(exc))
            # 다 읽었으면 사본을 들고 있을 이유가 없다. 상태를 먼저 적고 버린다 —
            # 순서가 반대면 지우는 데 실패했을 때 「끝났다」가 안 적힌다.
            outcome = _done(True)
            _discard_original(document)
            return outcome
        if state in {"FAILED", "CANCELLED", "TIMED_OUT"}:
            return _done(False, detail=_worker_failure_detail(result, state))

    # **아직 도는 중이다.** 실패로 적지 않는다 — 다음 질문에서는 끝나 있을 수 있다.
    return {"doc_id": doc_id, "ok": False, "detail": "아직 준비 중입니다(처리가 계속되고 있습니다)."}
