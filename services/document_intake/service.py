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

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from apps.connectors.clients import download_drive_file, list_drive_files
from apps.connectors.oauth import OAuthError
from backend.db import AccountRepository, DocumentRepository, TeamFolderRepository
from backend.db.document_pipeline import PipelineDocumentRepository
from backend.db.errors import RepositoryError
from backend.services.storage import build_key
from backend.services.storage import save as save_document
from services.document_pipeline.errors import DocumentPipelineError, PipelineConfigurationError

logger = logging.getLogger(__name__)


@dataclass
class IntakeResult:
    """무엇이 새로 들어왔고 무엇이 안 됐는가.

    **숫자만 돌려주지 않는다.** 안 된 것은 이유와 함께 남겨야 「연결은 됐는데
    문서가 없다」를 사람에게 설명할 수 있다.
    """

    registered: list[str] = field(default_factory=list)
    #: 본문 청크·임베딩까지 올라간 문서. 등록(`registered`)과 나눠 센다 —
    #: 등록만 된 문서는 목록에 보이지만 **문장 근거를 내지 못한다.**
    indexed: list[str] = field(default_factory=list)
    failed: list[dict[str, str]] = field(default_factory=list)
    #: 저장소를 아예 못 읽은 경우. 이때는 위 셋이 모두 비어 있어도 「문서가
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
        result.registered = [row["file_name"] for row in created]

    _fetch_originals(account_id=account_id, team_id=team_id, result=result)
    _index_all(account_id=account_id, team_id=team_id, result=result)
    return result


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


def promote_to_searchable(*, account_id: str, doc_id: str) -> dict[str, Any]:
    """문서 하나를 **본문 검색 가능**한 상태로 올린다.

    요약까지만 되어 있던 문서를 청크로 쪼개 임베딩한다.

    부르는 곳이 셋이다 — 폴더를 저장한 뒤 도는 전량 색인(`_index_all`), 검색이
    좁힌 후보 중 아직 청크가 없는 문서, 그리고 기준 문서로 지정된 문서. 앞의
    것이 정상 경로이고 뒤의 둘은 **아직 전량 색인이 닿지 않은 문서를 그 자리에서
    끌어올리는** 보충 경로다(워커가 순차라 폴더가 크면 시차가 생긴다).

    끝났는지 여기서 기다린다. 부르는 쪽이 도구라 「제출했습니다」로 끝내면
    그 턴 안에서 쓸 수가 없다.
    """

    from django.conf import settings

    from services.document_pipeline.runpod_client import job_status, submit_document_job
    from services.document_pipeline.signing import signed_download_url

    from backend.db.document_pipeline import PersonalDocumentRepository

    document = PipelineDocumentRepository.get_for_processing(doc_id=doc_id, account_id=account_id)
    if not document["storage_key"]:
        return {"doc_id": doc_id, "ok": False, "detail": "원문을 아직 받지 않았습니다."}

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

    deadline = time.monotonic() + PROMOTE_WAIT_SECONDS
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
            PipelineDocumentRepository.ingest(expected_doc=document, result=output)
            return _done(True)
        if state in {"FAILED", "CANCELLED", "TIMED_OUT"}:
            return _done(False, detail=f"문서 처리 실패({state})")

    # **아직 도는 중이다.** 실패로 적지 않는다 — 다음 질문에서는 끝나 있을 수 있다.
    return {"doc_id": doc_id, "ok": False, "detail": "아직 준비 중입니다(처리가 계속되고 있습니다)."}
