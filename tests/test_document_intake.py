"""`services/document_intake/service.py`의 배치 실패 처리 단위 테스트.

전체 파이프라인(등록·다운로드·요약·색인)을 다 재현하지 않는다. 여기서 보는
것은 **"어떤 실패가 배치를 멈추고 어떤 실패가 그 한 건으로 끝나는가"** 하나다
(2026-08-20 자격증명, 2026-08-24 전량 색인).
"""

import json
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.connectors.oauth import OAuthError
from backend.services.storage import content_hash
from services.document_intake.service import (
    IntakeResult,
    _fetch_originals,
    _index_all,
    _refetch_changed,
    _worker_failure_detail,
    promote_to_searchable,
    sync_drive_changes,
)
from services.document_pipeline.errors import PipelineConfigurationError, RunPodRequestError


def _pending(doc_id, file_name):
    return {
        "doc_id": doc_id,
        "file_name": file_name,
        "storage_key": None,
        "src_file_id": f"SRC-{doc_id}",
        "mime_type": "application/pdf",
    }


@patch("services.document_intake.service.DocumentRepository")
@patch("services.document_intake.service.download_drive_file")
class FetchAndSummarizeCredentialShortCircuitTests(SimpleTestCase):
    """자격증명 문제(`OAuthError`)는 같은 계정·같은 커넥터로 도는 남은 모든
    대기 문서에 반드시 똑같이 재현된다 — 첫 건에서 막히면 나머지는 더
    시도하지 않는다. 파일 하나만의 문제(`OSError` 등)는 그 한 건으로 끝나야
    하는 기존 규칙(모듈 docstring) 그대로 유지되는지도 같이 본다.
    """

    def test_자격증명_오류면_남은_문서를_더_받으려_하지_않는다(self, download, documents):
        documents.list_pending_download.return_value = [
            _pending("D1", "a.pdf"),
            _pending("D2", "b.pdf"),
            _pending("D3", "c.pdf"),
        ]
        download.side_effect = OAuthError("Google Drive 인증이 만료되었습니다.")

        result = IntakeResult()
        _fetch_originals(account_id="UA001", team_id="TM001", result=result)

        self.assertEqual(download.call_count, 1, "첫 건에서 막히면 나머지는 더 시도하면 안 된다")
        self.assertEqual(len(result.failed), 3, "대기 중이던 3건 전부에 실패 사유가 남아야 한다")
        self.assertTrue(all(row["detail"] == "OAuthError" for row in result.failed))

    def test_파일_하나만의_문제면_나머지는_계속_시도한다(self, download, documents):
        documents.list_pending_download.return_value = [
            _pending("D1", "a.pdf"),
            _pending("D2", "b.pdf"),
        ]
        download.side_effect = OSError("disk full")

        result = IntakeResult()
        _fetch_originals(account_id="UA001", team_id="TM001", result=result)

        self.assertEqual(download.call_count, 2, "파일 개별 문제는 그 한 건의 실패로 끝나야 한다")
        self.assertEqual(len(result.failed), 2)


@patch("services.document_intake.service.promote_to_searchable")
@patch("services.document_intake.service.PipelineDocumentRepository")
class IndexAllTests(SimpleTestCase):
    """폴더를 저장하면 **그 폴더 문서 전부**가 본문 색인까지 가야 한다(2026-08-24).

    전에는 요약에서 끊고 대화 중 좁혀진 문서만 승격시켰다. 그러면 폴더에 있는데도
    문장 근거를 못 내는 문서가 계속 남는다.
    """

    def test_대기_문서를_전부_색인한다(self, repository, promote):
        repository.list_pending_index.return_value = ["DC001", "DC002", "DC003"]
        promote.side_effect = lambda **kw: {"doc_id": kw["doc_id"], "ok": True}

        result = IntakeResult()
        _index_all(account_id="UA001", team_id="TM001", result=result)

        self.assertEqual(promote.call_count, 3, "대기 중인 문서는 하나도 빠지면 안 된다")
        self.assertEqual(result.indexed, ["DC001", "DC002", "DC003"])
        self.assertEqual(result.failed, [])

    def test_한_건이_실패해도_나머지는_계속한다(self, repository, promote):
        repository.list_pending_index.return_value = ["DC001", "DC002", "DC003"]

        def _promote(*, account_id, doc_id):
            if doc_id == "DC002":
                raise RunPodRequestError("워커가 응답하지 않습니다.")
            return {"doc_id": doc_id, "ok": True}

        promote.side_effect = _promote

        result = IntakeResult()
        _index_all(account_id="UA001", team_id="TM001", result=result)

        self.assertEqual(promote.call_count, 3, "한 건의 문제로 배치가 멈추면 안 된다")
        self.assertEqual(result.indexed, ["DC001", "DC003"])
        self.assertEqual(len(result.failed), 1)
        self.assertEqual(result.failed[0]["detail"], "RunPodRequestError")

    def test_설정이_없으면_남은_문서를_더_시도하지_않는다(self, repository, promote):
        """`PipelineConfigurationError` 는 RunPod 설정 자체가 없다는 뜻이라 남은
        문서도 전부 같은 이유로 실패한다 — 자격증명 실패와 같은 규칙이다."""

        repository.list_pending_index.return_value = ["DC001", "DC002", "DC003"]
        promote.side_effect = PipelineConfigurationError("필수 RunPod 설정이 없습니다")

        result = IntakeResult()
        _index_all(account_id="UA001", team_id="TM001", result=result)

        self.assertEqual(promote.call_count, 1, "첫 건에서 막히면 나머지는 더 시도하면 안 된다")
        self.assertEqual(len(result.failed), 3, "대기 중이던 3건 전부에 사유가 남아야 한다")
        self.assertTrue(all(row["detail"] == "PipelineConfigurationError" for row in result.failed))

    def test_시간_안에_못_끝낸_문서는_실패로_남아_다음_회차가_집는다(self, repository, promote):
        """승격은 240초에서 기다리기를 포기하고 `ok=False` 로 돌아온다. 색인된
        것으로 세면 안 된다 — 다음 호출이 다시 집어야 한다."""

        repository.list_pending_index.return_value = ["DC001"]
        promote.return_value = {"doc_id": "DC001", "ok": False, "detail": "아직 준비 중입니다"}

        result = IntakeResult()
        _index_all(account_id="UA001", team_id="TM001", result=result)

        self.assertEqual(result.indexed, [])
        self.assertEqual(result.failed[0]["detail"], "아직 준비 중입니다")


def _changed(doc_id, file_name, *, content_hash, drive_modified="2026-08-24T09:00:00Z"):
    return {
        "doc_id": doc_id,
        "src_file_id": f"SRC-{doc_id}",
        "file_name": file_name,
        "mime_type": "application/pdf",
        "src_modified_at": None,
        "content_hash": content_hash,
        "drive_modified_at": drive_modified,
    }


@patch("services.document_intake.service.save_document")
@patch("services.document_intake.service.download_drive_file")
@patch("services.document_intake.service.DocumentRepository")
class RefetchChangedTests(SimpleTestCase):
    """Drive 에서 고쳐진 문서를 다시 받는다(2026-08-24).

    없으면 기획서를 개정해도 우리는 영원히 등록 시점의 판으로 답한다.

    **`modifiedTime` 만으로 판단하지 않는다.** 이름 변경·공유 설정 변경·이동에도
    그 값은 오른다 — 그대로 믿고 재파싱하면 내용이 그대로인 문서로 GPU 를 태운다.
    """

    def test_내용이_바뀌었으면_다시_받아_저장한다(self, documents, download, save):
        documents.list_changed_on_drive.return_value = [
            _changed("DC001", "기획서.pdf", content_hash="sha256:old")
        ]
        download.return_value = {"content": b"new bytes", "mime_type": "application/pdf",
                                 "revision": "REV-2"}

        result = IntakeResult()
        _refetch_changed(
            account_id="UA001", team_id="TM001",
            live_modified={"SRC-DC001": "2026-08-24T09:00:00Z"}, result=result,
        )

        save.assert_called_once()
        self.assertEqual(result.refreshed, ["기획서.pdf"])
        stored = documents.mark_stored.call_args.kwargs
        self.assertEqual(stored["revision"], "REV-2", "새 revision 이 들어가야 옛 청크가 빠진다")
        self.assertEqual(stored["src_modified_at"], "2026-08-24T09:00:00Z")

    def test_내용이_같으면_저장도_재색인도_안_한다(self, documents, download, save):
        """`modifiedTime` 만 오른 경우다. 시각만 맞춰 두지 않으면 다음 스캔이
        같은 문서를 또 내려받는다."""

        same = content_hash(b"same bytes")
        documents.list_changed_on_drive.return_value = [
            _changed("DC001", "기획서.pdf", content_hash=same)
        ]
        download.return_value = {"content": b"same bytes", "mime_type": "application/pdf",
                                 "revision": "REV-1"}

        result = IntakeResult()
        _refetch_changed(
            account_id="UA001", team_id="TM001",
            live_modified={"SRC-DC001": "2026-08-24T09:00:00Z"}, result=result,
        )

        save.assert_not_called()
        documents.mark_stored.assert_not_called()
        documents.mark_unchanged.assert_called_once()
        self.assertEqual(result.refreshed, [], "내용이 그대로면 갱신으로 세지 않는다")

    def test_자격증명_오류면_남은_문서를_더_받으려_하지_않는다(self, documents, download, save):
        documents.list_changed_on_drive.return_value = [
            _changed("DC001", "a.pdf", content_hash="sha256:old"),
            _changed("DC002", "b.pdf", content_hash="sha256:old"),
        ]
        download.side_effect = OAuthError("Google Drive 인증이 만료되었습니다.")

        result = IntakeResult()
        _refetch_changed(
            account_id="UA001", team_id="TM001",
            live_modified={"SRC-DC001": "x", "SRC-DC002": "x"}, result=result,
        )

        self.assertEqual(download.call_count, 1)
        self.assertEqual(len(result.failed), 2)

    def test_바뀐_문서가_없으면_아무것도_안_받는다(self, documents, download, save):
        documents.list_changed_on_drive.return_value = []

        result = IntakeResult()
        _refetch_changed(
            account_id="UA001", team_id="TM001", live_modified={"SRC-DC001": "x"}, result=result,
        )

        download.assert_not_called()
        self.assertEqual(result.refreshed, [])


def _change(file_id, *, removed=False, trashed=False, modified="2026-08-24T10:00:00Z"):
    return {
        "file_id": file_id,
        "removed": removed,
        "trashed": trashed,
        "name": f"{file_id}.pdf",
        "mime_type": "application/pdf",
        "modified_at": modified,
    }


@patch("services.document_intake.service._index_all")
@patch("services.document_intake.service._refetch_changed")
@patch("services.document_intake.service.AccountRepository")
@patch("services.document_intake.service.DocumentRepository")
@patch("services.document_intake.service.list_drive_changes")
@patch("services.document_intake.service.drive_start_page_token")
@patch("services.document_intake.service.ConnectorRepository")
class SyncDriveChangesTests(SimpleTestCase):
    """대화를 시작할 때 Drive 변경분만 따라간다(2026-08-24).

    폴더 스캔은 폴더마다 API 를 2번 부르므로 비싸서 「폴더 저장 시」만 돌았다.
    Changes API 는 변화가 없으면 호출 1번이라 대화마다 물어도 된다.
    """

    TARGET = {"conn_id": "CN001", "account_id": "UA-LEADER", "sync_cursor": "TOKEN-1"}

    def test_커서가_없으면_기준점만_잡고_끝낸다(
        self, connectors, start_token, changes, documents, accounts, refetch, index
    ):
        """연결 이전의 변경까지 거슬러 올라갈 이유가 없다 — 처음 등록은 폴더
        스캔이 이미 했다."""

        connectors.drive_sync_target.return_value = dict(self.TARGET, sync_cursor=None)
        start_token.return_value = "TOKEN-START"

        sync_drive_changes(account_id="UA002")

        changes.assert_not_called()
        connectors.set_sync_cursor.assert_called_once_with(
            conn_id="CN001", cursor_value="TOKEN-START"
        )

    def test_지워진_문서를_사람에게_묻지_않고_내린다(
        self, connectors, start_token, changes, documents, accounts, refetch, index
    ):
        """Changes API 가 `removed`·`trashed` 를 명시하므로 폴더 스캔 시절의
        모호함(휴지통·완전삭제·폴더 밖 이동 구별 불가)이 사라진다."""

        connectors.drive_sync_target.return_value = dict(self.TARGET)
        changes.return_value = ([_change("F1", removed=True), _change("F2", trashed=True)], "TOKEN-2")
        accounts.team_id.return_value = "TM001"
        documents.doc_ids_for_source.return_value = ["DC001", "DC002"]

        result = sync_drive_changes(account_id="UA002")

        documents.mark_removed_from_drive.assert_called_once_with(
            account_id="UA-LEADER", doc_ids=["DC001", "DC002"]
        )
        self.assertEqual(result.removed, ["DC001", "DC002"])
        refetch.assert_not_called()

    def test_고쳐진_문서는_재수신_경로로_넘긴다(
        self, connectors, start_token, changes, documents, accounts, refetch, index
    ):
        connectors.drive_sync_target.return_value = dict(self.TARGET)
        changes.return_value = ([_change("F1")], "TOKEN-2")
        accounts.team_id.return_value = "TM001"
        documents.doc_ids_for_source.return_value = []

        sync_drive_changes(account_id="UA002")

        self.assertEqual(refetch.call_args.kwargs["live_modified"], {"F1": "2026-08-24T10:00:00Z"})
        # 재수신이 revision 을 바꾸면 색인 대기로 돌아온다 — 그래서 이어서 돈다.
        index.assert_called_once()

    def test_커서는_처리가_끝난_뒤에_옮긴다(
        self, connectors, start_token, changes, documents, accounts, refetch, index
    ):
        """먼저 저장하면 처리 중에 죽었을 때 그 구간을 영영 다시 못 본다.
        같은 변경을 두 번 보는 쪽이 낫다 — 해시가 같으면 아무것도 안 한다."""

        order = []
        connectors.drive_sync_target.return_value = dict(self.TARGET)
        changes.return_value = ([_change("F1")], "TOKEN-2")
        accounts.team_id.return_value = "TM001"
        documents.doc_ids_for_source.return_value = []
        refetch.side_effect = lambda **kw: order.append("refetch")
        connectors.set_sync_cursor.side_effect = lambda **kw: order.append("cursor")

        sync_drive_changes(account_id="UA002")

        self.assertEqual(order, ["refetch", "cursor"])

    def test_연결이나_폴더가_없으면_아무것도_안_한다(
        self, connectors, start_token, changes, documents, accounts, refetch, index
    ):
        connectors.drive_sync_target.return_value = None

        result = sync_drive_changes(account_id="UA002")

        changes.assert_not_called()
        start_token.assert_not_called()
        self.assertEqual(result.removed, [])

    def test_자격증명이_막히면_대화를_막지_않고_끝낸다(
        self, connectors, start_token, changes, documents, accounts, refetch, index
    ):
        connectors.drive_sync_target.return_value = dict(self.TARGET)
        changes.side_effect = OAuthError("Google Drive 인증이 만료되었습니다.")

        result = sync_drive_changes(account_id="UA002")

        self.assertEqual(result.storage_error, "OAuthError")
        documents.mark_removed_from_drive.assert_not_called()
        connectors.set_sync_cursor.assert_not_called()


class WorkerFailureDetailTests(SimpleTestCase):
    """실패 사유가 화면까지 가는지 본다.

    `doc.index_detail` 은 2026-08-24에 「왜 안 되는지」를 화면이 말하게 하려고
    만든 칸이다. 그런데 실패 경로가 RunPod 이 준 워커 오류를 버리고 상태값만
    적고 있어서, 실제로 뜬 문구가 「문서 처리 실패(FAILED)」였다 — 칸만 있고
    말은 없는 상태였다.
    """

    #: RunPod 이 실제로 돌려준 모양. `error` 는 **JSON 문자열**이다.
    WORKER_ERROR = json.dumps(
        {
            "error_type": "<class 'pipeline.InvalidDocumentError'>",
            "error_message": "표 #/tables/14의 셀 구조가 비어 있습니다.",
            "error_traceback": "Traceback (most recent call last):\n  ...\n",
        }
    )

    def test_워커가_말한_이유를_그대로_쓴다(self):
        detail = _worker_failure_detail({"error": self.WORKER_ERROR}, "FAILED")

        self.assertEqual(detail, "표 #/tables/14의 셀 구조가 비어 있습니다.")

    def test_트레이스백은_넣지_않는다(self):
        """사람이 읽는 칸이다. 스택은 워커 로그에 있다."""

        detail = _worker_failure_detail({"error": self.WORKER_ERROR}, "FAILED")

        self.assertNotIn("Traceback", detail)

    def test_JSON_이_아니어도_상태값보다는_낫게_쓴다(self):
        detail = _worker_failure_detail({"error": "worker exited unexpectedly"}, "FAILED")

        self.assertEqual(detail, "worker exited unexpectedly")

    def test_사유가_없으면_상태값으로_돌아간다(self):
        """오류 칸이 비어 오는 경우가 있다(CANCELLED·TIMED_OUT). 그때는 상태라도 남긴다."""

        for payload in ({}, {"error": ""}, {"error": None}):
            with self.subTest(payload=payload):
                self.assertEqual(
                    _worker_failure_detail(payload, "TIMED_OUT"), "문서 처리 실패(TIMED_OUT)"
                )

    def test_아주_긴_사유는_잘라_넣는다(self):
        """화면에 뜨는 칸이라 통째로 넣으면 읽을 수 없다."""

        long = json.dumps({"error_message": "가" * 900})

        self.assertEqual(len(_worker_failure_detail({"error": long}, "FAILED")), 500)


@patch("services.document_intake.service.time.sleep", lambda _: None)
@patch("backend.db.document_pipeline.PersonalDocumentRepository")
@patch("services.document_pipeline.signing.signed_download_url", return_value="https://x/y")
@patch("services.document_pipeline.runpod_client.job_status")
@patch("services.document_pipeline.runpod_client.submit_document_job", return_value={"id": "J1"})
@patch("services.document_intake.service.PipelineDocumentRepository")
class PromoteWritesWorkerReasonTests(SimpleTestCase):
    """`promote_to_searchable` 이 **실제로** 그 사유를 칸에 넣는지 본다.

    앞의 `WorkerFailureDetailTests` 는 함수만 본다 — 호출부가 예전처럼
    `f"문서 처리 실패({state})"` 로 되돌아가도 그 테스트는 통과한다. 오늘 고친
    것은 「화면에 진짜 이유가 뜬다」이므로, 저장되는 값까지 봐야 지켜진다.
    """

    def test_저장되는_사유가_워커가_말한_것이다(
        self, pipeline_repo, submit, status, url, personal_repo
    ):
        pipeline_repo.get_for_processing.return_value = {
            "storage_key": "k", "cur_revision": "r", "mime_type": "text/markdown",
        }
        status.return_value = {
            "status": "FAILED",
            "error": json.dumps({"error_message": "표 #/tables/14의 셀 구조가 비어 있습니다."}),
        }

        outcome = promote_to_searchable(account_id="UA002", doc_id="DC005")

        self.assertFalse(outcome["ok"])
        self.assertEqual(outcome["detail"], "표 #/tables/14의 셀 구조가 비어 있습니다.")
        saved = personal_repo.set_index_status.call_args.kwargs
        self.assertEqual(saved["status"], "FAILED")
        self.assertEqual(saved["detail"], "표 #/tables/14의 셀 구조가 비어 있습니다.")
