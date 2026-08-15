"""연결된 저장소의 파일을 요약까지 받아들인다.

한 건이 이상하다고 나머지를 멈추지 않는다. 팀 문서 전부에 도는 일이라 한 건의
실패는 그 한 건으로 끝나야 한다 — 옛 API 뷰들이 지키던 규칙을 그대로 가져온다.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from apps.connectors.clients import download_drive_file, list_drive_files
from apps.connectors.oauth import OAuthError
from backend.db import AccountRepository, DocumentRepository, TeamFolderRepository
from backend.db.document_pipeline import DocMetaRepository, PipelineDocumentRepository
from backend.db.errors import RepositoryError
from backend.services.storage import build_key
from backend.services.storage import save as save_document
from backend.services.storage import load as load_document
from services.document_meta import as_row as doc_meta_row
from services.document_meta import build as build_doc_meta
from services.document_pipeline.errors import DocumentPipelineError

logger = logging.getLogger(__name__)


@dataclass
class IntakeResult:
    """무엇이 새로 들어왔고 무엇이 안 됐는가.

    **숫자만 돌려주지 않는다.** 안 된 것은 이유와 함께 남겨야 「연결은 됐는데
    문서가 없다」를 사람에게 설명할 수 있다.
    """

    registered: list[str] = field(default_factory=list)
    summarized: list[str] = field(default_factory=list)
    failed: list[dict[str, str]] = field(default_factory=list)
    #: 저장소를 아예 못 읽은 경우. 이때는 위 셋이 모두 비어 있어도 「문서가
    #: 없다」는 뜻이 아니다.
    storage_error: str | None = None


def intake_connector_documents(*, account_id: str, limit: int = 20) -> IntakeResult:
    """연결된 폴더의 파일을 `doc` 에 넣고 내려받아 요약까지 만든다.

    `limit` 은 한 번에 새로 받아들이는 문서 수다. 요약은 문서당 LLM 1회 +
    임베딩 1개라 싼 편이지만 공짜는 아니고, 폴더가 크면 첫 호출이 통째로
    길어진다 — 나머지는 다음 호출이 이어받는다.

    **이미 있는 것은 건드리지 않는다.** 등록된 파일은 건너뛰고, 요약이 있는
    문서는 다시 만들지 않는다. 여러 번 불러도 안전해야 저장소가 바뀔 때마다
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
        for folder in folders:
            for item in list_drive_files(
                account_id=account_id,
                parent_id=folder["external_folder_id"],
                max_depth=folder.get("max_depth") or 1,
            ):
                # 파싱할 수 없는 형식은 받아들이지 않는다. 목록에는 보여 주되
                # (`document_list`) 저장소에 넣어 봐야 읽을 수 없다.
                if not item["supported"] or item["file_id"] in known:
                    continue
                candidates.append(item)
                if len(candidates) >= limit:
                    break
            if len(candidates) >= limit:
                break
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
                    }
                    for item in candidates
                ],
            )
        except (RepositoryError, Exception) as exc:  # noqa: BLE001
            logger.exception("문서 등록 실패")
            result.storage_error = exc.__class__.__name__
            return result
        # 지워진 문서의 메타가 남아 있으면 새 문서가 그 요약을 물려받는다
        # (`DocMetaRepository.purge` 주석). 등록 직후 그 자리를 비운다.
        DocMetaRepository.purge([row["doc_id"] for row in created])
        result.registered = [row["file_name"] for row in created]

    _fetch_and_summarize(account_id=account_id, team_id=team_id, result=result)
    return result


def _fetch_and_summarize(*, account_id: str, team_id: str, result: IntakeResult) -> None:
    """원문을 받아 요약·요약임베딩을 만든다.

    **다운로드와 요약을 한 함수에 둔다.** 옛 화면은 둘을 따로 불렀지만, 그건
    진행을 한 단계씩 보여주려던 것이었다 — 부르는 쪽이 화면이 아니면 나눌 이유가
    없고, 나누면 「받아만 두고 요약이 없는」 상태가 생긴다.
    """

    for target in DocumentRepository.list_pending_download(account_id):
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
        except (OAuthError, OSError, RepositoryError) as exc:
            logger.exception("원문 수신 실패: %s", target["doc_id"])
            result.failed.append({"file_name": target["file_name"], "detail": exc.__class__.__name__})

    for doc_id in DocMetaRepository.pending_doc_ids(team_id):
        try:
            document = PipelineDocumentRepository.get_for_processing(
                doc_id=doc_id, account_id=account_id
            )
            if not document["storage_key"]:
                continue
            meta = build_doc_meta(
                doc_id=doc_id,
                content=load_document(document["storage_key"]),
                mime_type=document["mime_type"],
                file_name=document["file_name"],
            )
            DocMetaRepository.upsert(doc_meta_row(meta))
        except (ValueError, OSError, RepositoryError, DocumentPipelineError) as exc:
            logger.exception("문서 요약 실패: %s", doc_id)
            result.failed.append({"file_name": doc_id, "detail": exc.__class__.__name__})
            continue
        result.summarized.append(document["file_name"])


#: 청크 파싱·임베딩 한 건을 기다려 주는 한계(초).
#:
#: RunPod 워커가 모델을 이미지에 넣지 않아 첫 실행이 몇 분이다. 여기서 무한정
#: 기다리면 대화가 멈춘 것처럼 보이므로, 못 끝내면 **그 사실을 답에 담아** 넘긴다
#: — 조용히 실패하면 「관련 문서가 없다」로 읽힌다.
PROMOTE_WAIT_SECONDS = 240


def promote_to_searchable(*, account_id: str, doc_id: str) -> dict[str, Any]:
    """문서 하나를 **본문 검색 가능**한 상태로 올린다.

    요약까지만 되어 있던 문서를 청크로 쪼개 임베딩한다. 검색이 후보를 좁힌
    **그 문서에만** 도는 것이 요점이다 — 전 문서에 미리 돌리면, 쓰지도 않을
    문서까지 파싱·임베딩하게 된다(2026-08-15 PM).

    끝났는지 여기서 기다린다. 부르는 쪽이 도구라 「제출했습니다」로 끝내면
    그 턴 안에서 쓸 수가 없다.
    """

    from django.conf import settings

    from services.document_pipeline.runpod_client import job_status, submit_document_job
    from services.document_pipeline.signing import signed_download_url

    document = PipelineDocumentRepository.get_for_processing(doc_id=doc_id, account_id=account_id)
    if not document["storage_key"]:
        return {"doc_id": doc_id, "ok": False, "detail": "원문을 아직 받지 않았습니다."}

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

    deadline = time.monotonic() + PROMOTE_WAIT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(3)
        result = job_status(job["id"])
        state = result.get("status")
        if state == "COMPLETED":
            output = result.get("output")
            if not isinstance(output, dict):
                return {"doc_id": doc_id, "ok": False, "detail": "처리 결과가 비어 있습니다."}
            # 완료 시점에 바로 적재한다. RunPod 는 완료 결과를 제한된 시간만
            # 보관해서 나중에 다시 받아 오면 되겠지 하고 미룰 수 없다.
            PipelineDocumentRepository.ingest(expected_doc=document, result=output)
            return {"doc_id": doc_id, "ok": True}
        if state in {"FAILED", "CANCELLED", "TIMED_OUT"}:
            return {"doc_id": doc_id, "ok": False, "detail": f"문서 처리 실패({state})"}

    # **아직 도는 중이다.** 실패로 적지 않는다 — 다음 질문에서는 끝나 있을 수 있다.
    return {"doc_id": doc_id, "ok": False, "detail": "아직 준비 중입니다(처리가 계속되고 있습니다)."}
