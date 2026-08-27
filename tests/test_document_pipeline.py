import importlib
import json
import os
import pathlib
import tempfile
import zlib
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from apps.accounts.tokens import issue_token
from runpod_worker.pipeline import (
    ChunkValidationError,
    _convert,
    _has_text_layer,
    _generic_row_records,
    _product_records,
    _screen_oversized,
)
from services.document_pipeline.errors import PipelineConfigurationError, RunPodRequestError
from services.document_pipeline.signing import read_download_token, signed_download_url


def auth_header(account_id="UA001"):
    return {"authorization": f"Bearer {issue_token(account_id)}"}


def table(cells, rows=2, cols=3):
    return {
        "self_ref": "#/tables/0",
        "data": {"num_rows": rows, "num_cols": cols, "table_cells": cells},
        "prov": [{"page_no": 2}],
    }


def cell(text, sr, er, sc, ec, **flags):
    return {
        "text": text,
        "start_row_offset_idx": sr,
        "end_row_offset_idx": er,
        "start_col_offset_idx": sc,
        "end_col_offset_idx": ec,
        **flags,
    }


class OversizedChunkTests(SimpleTestCase):
    """한도를 넘는 청크 하나가 문서 전체를 죽이지 않는지.

    실제로 제안요청서 한 건이 749 토큰짜리 청크 하나 때문에 본문 163블록까지
    통째로 버려졌다(2026-08-04). 토큰 계산은 주입해서 docling 없이 검증한다.
    """

    def _chunk(self, text, chunk_type="table", refs=("#/tables/0",)):
        return {"chunk_type": chunk_type, "text": text, "source_refs": list(refs)}

    def _count(self, text):
        return len(text)

    def test_oversized_table_row_is_dropped_not_fatal(self):
        chunks = [
            self._chunk("짧은 표 행"),
            self._chunk("x" * 40),
            self._chunk("본문", chunk_type="text", refs=("#/texts/3",)),
        ]

        kept, dropped = _screen_oversized(chunks, {"#/tables/0"}, 20, self._count)

        self.assertEqual([c["text"] for c in kept], ["짧은 표 행", "본문"])
        self.assertEqual(len(dropped), 1)
        self.assertEqual(dropped[0]["token_count"], 40)
        self.assertEqual(dropped[0]["source_refs"], ["#/tables/0"])

    def test_text_chunk_mixed_with_a_table_is_dropped(self):
        """표와 본문이 섞인 청크도 표 몫이라 버린다 — 표는 행 단위로 다시 만든다."""

        chunks = [self._chunk("y" * 40, chunk_type="text", refs=("#/texts/1", "#/tables/0"))]

        kept, dropped = _screen_oversized(
            chunks + [self._chunk("남는 것")], {"#/tables/0"}, 20, self._count
        )

        self.assertEqual([c["text"] for c in kept], ["남는 것"])
        self.assertEqual(len(dropped), 1)

    def test_oversized_body_text_still_fails(self):
        """표가 안 걸렸는데 넘친 것은 우리 청킹 문제다. 조용히 버리지 않는다.

        멀쩡한 청크를 함께 넣는다. 넘친 것 하나뿐이면 「남은 청크가 없다」는
        다른 이유로도 같은 예외가 나서, 이 분기를 지웠는지 알 수 없다.
        """

        chunks = [
            self._chunk("남는 것"),
            self._chunk("z" * 40, chunk_type="text", refs=("#/texts/1",)),
        ]

        with self.assertRaises(ChunkValidationError):
            _screen_oversized(chunks, {"#/tables/0"}, 20, self._count)

    def test_all_chunks_dropped_is_fatal(self):
        """전부 버려지면 빈 문서를 적재하게 된다. 그건 실패다."""

        chunks = [self._chunk("x" * 40), self._chunk("y" * 40)]

        with self.assertRaises(ChunkValidationError):
            _screen_oversized(chunks, {"#/tables/0"}, 20, self._count)

    def test_empty_text_is_fatal(self):
        with self.assertRaises(ChunkValidationError):
            _screen_oversized([self._chunk("   ")], {"#/tables/0"}, 20, self._count)


class TableChunkingTests(SimpleTestCase):
    def test_product_columns_preserve_source_order_and_values(self):
        source = table(
            [
                cell("Model", 0, 1, 0, 1, column_header=True),
                cell("B", 0, 1, 1, 2, column_header=True),
                cell("A", 0, 1, 2, 3, column_header=True),
                cell("압력", 1, 2, 0, 1, row_header=True),
                cell("10 bar", 1, 2, 1, 2),
                cell("20 bar", 1, 2, 2, 3),
            ]
        )
        records = _product_records(source, 0)
        self.assertEqual([r["meta"]["product"] for r in records], ["B", "A"])
        self.assertIn("압력: 10 bar", records[0]["text"])

    def test_non_product_table_uses_generic_rows(self):
        source = table(
            [
                cell("요구사항", 0, 1, 0, 1, column_header=True),
                cell("담당", 0, 1, 1, 2, column_header=True),
                cell("상태", 0, 1, 2, 3, column_header=True),
                cell("로그인", 1, 2, 0, 1),
                cell("백엔드", 1, 2, 1, 2),
                cell("진행", 1, 2, 2, 3),
            ]
        )
        self.assertEqual(_product_records(source, 0), [])
        rows = _generic_row_records(source, 0)
        self.assertEqual(len(rows), 1)
        self.assertIn("요구사항: 로그인", rows[0]["text"])


class SigningTests(SimpleTestCase):
    """서명은 `doc_id`+`revision`만 묶는다(2026-08-04).

    `project_id`를 함께 서명하던 시절이 있었는데, 문서 처리는 팀 단위라 이 시점에
    문서가 어느 프로젝트에 속할지 아직 정해지지 않았다(`doc.proj_id`가 NULL).
    """

    @override_settings(PUBLIC_BACKEND_BASE_URL="https://demo.example.com")
    def test_signed_url_round_trip(self):
        url = signed_download_url(doc_id="DC001", revision="rev-1")
        token = url.split("token=", 1)[1]
        self.assertEqual(
            read_download_token(token),
            {"doc_id": "DC001", "revision": "rev-1"},
        )

    @override_settings(PUBLIC_BACKEND_BASE_URL="https://demo.example.com")
    def test_url_carries_no_storage_path(self):
        """원문이 로컬 어디에 있는지는 RunPod에 알려 줄 이유가 없다."""

        url = signed_download_url(doc_id="DC001", revision="rev-1")

        self.assertNotIn("storage", url)
        self.assertTrue(url.startswith("https://demo.example.com/"))

    @override_settings(PUBLIC_BACKEND_BASE_URL="http://127.0.0.1:8000")
    def test_public_base_url_must_be_https(self):
        with self.assertRaises(PipelineConfigurationError):
            signed_download_url(doc_id="DC001", revision="rev-1")


class TunnelHostAllowanceTests(SimpleTestCase):
    """터널 호스트는 한 군데만 고치면 된다.

    `PUBLIC_BACKEND_BASE_URL` 과 `ALLOWED_HOSTS` 를 손으로 맞추게 뒀더니
    어긋났고, Django 가 DisallowedHost 로 400 을 줘서 워커가 원문을 못 받았다
    (2026-08-25 RunPod 콘솔 로그 10건). Quick Tunnel 은 띄울 때마다 주소가
    바뀌므로 고칠 곳이 둘이면 한쪽을 잊는다.
    """

    def _allowed_hosts(self, **environment):
        """주어진 환경변수로 설정 모듈을 다시 읽어 `ALLOWED_HOSTS` 를 본다."""

        import config.settings.base as settings_module

        try:
            with patch.dict(os.environ, environment):
                importlib.reload(settings_module)
                return list(settings_module.ALLOWED_HOSTS)
        finally:
            # 다른 테스트가 이 모듈을 그대로 쓰므로 원래 값으로 되돌린다.
            importlib.reload(settings_module)

    def test_터널_호스트가_저절로_허용된다(self):
        hosts = self._allowed_hosts(
            ALLOWED_HOSTS="localhost,127.0.0.1",
            PUBLIC_BACKEND_BASE_URL="https://establishment-behavioral-acres-heather.trycloudflare.com",
        )
        self.assertIn("establishment-behavioral-acres-heather.trycloudflare.com", hosts)
        self.assertIn("localhost", hosts)

    def test_이미_적혀_있으면_두_번_넣지_않는다(self):
        hosts = self._allowed_hosts(
            ALLOWED_HOSTS="localhost,demo.example.com",
            PUBLIC_BACKEND_BASE_URL="https://demo.example.com",
        )
        self.assertEqual(hosts.count("demo.example.com"), 1)

    def test_주소가_없으면_아무것도_붙지_않는다(self):
        """터널 없이 로컬만 쓰는 개발자가 있다. 빈 호스트를 넣으면 안 된다."""

        hosts = self._allowed_hosts(
            ALLOWED_HOSTS="localhost,127.0.0.1", PUBLIC_BACKEND_BASE_URL=""
        )
        self.assertEqual(hosts, ["localhost", "127.0.0.1"])


class SourceDocumentSelectionTests(SimpleTestCase):
    """기준 문서 선택이 프로젝트에 문서를 묶는다.

    **이 저장이 신규 프로젝트를 정의하는 행위다.** 기존 프로젝트에 문서를 붙이는
    것이 아니라, 기획서를 고르는 것이 곧 프로젝트를 만드는 것이라는 전제를 지킨다.
    """

    def _put(self, body):
        return self.client.put(
            "/api/projects/PJ001/source-documents/",
            body,
            content_type="application/json",
            headers=auth_header(),
        )

    @patch("apps.projects.api_views.PipelineDocumentRepository.list_ready_for_analysis")
    @patch("apps.projects.api_views.PipelineDocumentRepository.set_primary_document")
    def test_primary_document_is_saved(self, save, list_ready):
        list_ready.return_value = []

        response = self._put({"primary_document_id": "DC001"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(save.call_args.kwargs["primary_doc_id"], "DC001")

    @patch("apps.projects.api_views.PipelineDocumentRepository.list_ready_for_analysis")
    @patch("apps.projects.api_views.PipelineDocumentRepository.set_primary_document")
    def test_sub_documents_are_not_accepted(self, save, list_ready):
        """근거 문서는 사람이 고르지 않는다. 보내도 프로젝트에 묶이지 않는다."""

        list_ready.return_value = []

        response = self._put(
            {"primary_document_id": "DC001", "sub_document_ids": ["DC002", "DC003"]}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(save.call_args.kwargs, {
            "proj_id": "PJ001",
            "account_id": "UA001",
            "primary_doc_id": "DC001",
        })

    def test_requires_login(self):
        response = self.client.put(
            "/api/projects/PJ001/source-documents/",
            {"primary_document_id": "DC001"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)


@override_settings(
    RUNPOD_API_KEY="key",
    RUNPOD_ENDPOINT_ID="ep",
    RUNPOD_EXECUTION_TIMEOUT_MS=1000,
    RUNPOD_EMBED_WAIT_SECONDS=30,
)
class QueryEmbeddingTests(SimpleTestCase):
    """질의 임베딩이 워커 콜드 스타트를 견디는지.

    `/runsync` 는 자기 대기 창이 끝나면 아직 큐에 있어도 그대로 돌려준다. 그것을
    실패로 읽어서, 워커가 0으로 줄어 있던 날 이미 돈을 쓴 검색어 생성까지
    버려졌다(2026-08-05).
    """

    def _response(self, payload):
        mock = Mock(ok=True, status_code=200)
        mock.json.return_value = payload
        return mock

    def test_waits_for_a_cold_worker(self):
        from services.document_pipeline import runpod_client

        queued = self._response({"id": "job-1", "status": "IN_QUEUE"})
        done = self._response({"id": "job-1", "status": "COMPLETED", "output": {"embeddings": [[0.1] * 768]}})

        with patch.object(runpod_client.requests, "post", return_value=queued), patch.object(
            runpod_client.requests, "get", side_effect=[self._response({"status": "IN_PROGRESS"}), done]
        ) as get, patch.object(runpod_client.time, "sleep"):
            vectors = runpod_client.embed_queries(["역할과 자격 요건"])

        self.assertEqual(len(vectors), 1)
        self.assertEqual(len(vectors[0]), 768)
        # 큐에 있는 동안 계속 물었다.
        self.assertEqual(get.call_count, 2)

    def test_gives_up_after_the_deadline(self):
        """무한정 매달리지 않는다. 마지막 상태를 그대로 말한다."""

        from services.document_pipeline import runpod_client

        queued = self._response({"id": "job-1", "status": "IN_QUEUE"})

        with patch.object(runpod_client.requests, "post", return_value=queued), patch.object(
            runpod_client.requests, "get", return_value=self._response({"status": "IN_QUEUE"})
        ), patch.object(runpod_client.time, "sleep"), patch.object(
            runpod_client.time, "monotonic", side_effect=[0, 1, 999]
        ):
            with self.assertRaises(RunPodRequestError) as caught:
                runpod_client.embed_queries(["역할과 자격 요건"])

        self.assertIn("IN_QUEUE", str(caught.exception))


class TextLayerTests(SimpleTestCase):
    """OCR 을 걸지 말지 정하는 판정.

    **OCR 이 멀쩡한 텍스트를 덮어써서 망가뜨렸다**(2026-08-05). 제안요청서 본문이
    「중도탈락을」→「중도달락올」처럼 자모 단위로 치환돼 적재됐고, 그 글을 업무
    추출 에이전트가 읽었다. 같은 PDF 의 텍스트 레이어는 깨끗했다.
    """

    def _pdf(self, tmp, *, operators):
        """텍스트 연산자 `operators` 개를 담은 최소 PDF 를 만든다."""

        body = zlib.compress(b"BT (x) Tj ET " * operators)
        raw = b"%PDF-1.4\n1 0 obj<</Length 1>>stream\n" + body + b"\nendstream endobj\n%%EOF\n"
        target = tmp / "sample.pdf"
        target.write_bytes(raw)
        return target

    def test_programmatic_pdf_keeps_its_own_text(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self._pdf(pathlib.Path(directory), operators=300)
            self.assertTrue(_has_text_layer(target))

    def test_scanned_pdf_needs_ocr(self):
        """텍스트가 거의 없으면 스캔본이다. 여기서는 OCR 이 유일한 통로다."""

        with tempfile.TemporaryDirectory() as directory:
            target = self._pdf(pathlib.Path(directory), operators=5)
            self.assertFalse(_has_text_layer(target))

    def test_unreadable_path_does_not_raise(self):
        """판정이 못 되면 OCR 을 켜는 쪽으로 떨어진다 — 파싱 자체를 막지 않는다."""

        self.assertFalse(_has_text_layer(pathlib.Path("/no/such/file.pdf")))


class EnrichmentFallbackTests(SimpleTestCase):
    """깨진 페이지를 가진 PDF 를 문서 전체를 잃지 않고 살린다.

    전처리에서 죽은 페이지가 `conv_res.pages` 에서 빠지는데 보강 단계는 원래
    페이지 번호로 그 목록을 집는다 — `IndexError: list index out of range` 로
    문서 하나가 통째로 실패했다(2026-08-24 실측).
    """

    def _converter(self, *, fails_when_enriched):
        """`converter(use_ocr, enrich=...)` 를 흉내낸다."""

        def factory(use_ocr=True, enrich=True):
            engine = Mock()
            if enrich and fails_when_enriched:
                engine.convert.side_effect = RuntimeError("Pipeline StandardPdfPipeline failed")
            else:
                engine.convert.return_value = f"converted(enrich={enrich})"
            return engine

        return factory

    def test_보강이_죽인_pdf_는_보강을_끄고_살아난다(self):
        with patch(
            "runpod_worker.pipeline.converter", self._converter(fails_when_enriched=True)
        ):
            result, enriched = _convert(pathlib.Path("sample.pdf"), False)
        self.assertEqual(result, "converted(enrich=False)")
        self.assertFalse(enriched)

    def test_멀쩡한_문서는_보강을_켠_채로_끝난다(self):
        """되돌리기는 실패했을 때만이다 — 멀쩡한 문서가 차트를 잃으면 안 된다."""

        with patch(
            "runpod_worker.pipeline.converter", self._converter(fails_when_enriched=False)
        ):
            result, enriched = _convert(pathlib.Path("sample.pdf"), False)
        self.assertEqual(result, "converted(enrich=True)")
        self.assertTrue(enriched)

    def test_pdf_가_아니면_되돌리지_않는다(self):
        """위 오류는 PDF 파이프라인의 것이다. DOCX 가 죽는 이유는 다르다."""

        with patch(
            "runpod_worker.pipeline.converter", self._converter(fails_when_enriched=True)
        ):
            with self.assertRaises(RuntimeError):
                _convert(pathlib.Path("sample.docx"), False)

    def test_되돌린_시도도_실패하면_사유가_그대로_올라간다(self):
        """사유는 사람이 읽는 `index_detail` 로 간다 — 삼키면 안 된다."""

        def factory(use_ocr=True, enrich=True):
            engine = Mock()
            engine.convert.side_effect = RuntimeError("암호가 걸린 PDF 입니다")
            return engine

        with patch("runpod_worker.pipeline.converter", factory):
            with self.assertRaisesMessage(RuntimeError, "암호가 걸린 PDF 입니다"):
                _convert(pathlib.Path("sample.pdf"), False)


class EvidenceCitationTests(SimpleTestCase):
    """모델이 근거를 잘못 인용해도 추출 전체가 죽지 않아야 한다.

    36자 UUID 를 그대로 옮겨 적게 했더니 하나가 어긋나 5단계에서 전체가 실패했다
    (2026-08-05). 이제 `E1` 같은 짧은 번호로 인용하고, 모르는 번호는 그 업무에서만
    떨어뜨린다. 근거가 하나도 안 남은 업무는 만들지 않는다.
    """

    def _run(self, tasks):
        from services.task_extraction import service

        rows = [
            {"chunk_id": "aaaa-1", "doc_id": "DC001", "text": "가", "intent": "TASK_CORE",
             "query": "q", "retrieval_score": 0.9, "heading_path": []},
            {"chunk_id": "bbbb-2", "doc_id": "DC001", "text": "나", "intent": "TASK_CORE",
             "query": "q", "retrieval_score": 0.8, "heading_path": []},
        ]
        parsed = Mock(tasks=tasks, warnings=[])
        response = Mock(output_parsed=parsed)
        client = Mock()
        client.responses.parse.return_value = response

        with patch.object(service, "_client", return_value=client), patch.object(
            service, "embed_queries", return_value=[[0.0] * 768]
        ), patch.object(
            service, "_query_plan",
            return_value=service.QueryPlan(intent="TASK_CORE", queries=["q"], top_k=10),
        ), patch.object(
            service.VectorSearchRepository, "search", side_effect=[rows, [], [], []]
        ):
            events = list(
                service.extract_tasks_stream(
                    team_id="TE001",
                    primary_document={"doc_id": "DC001", "file_name": "plan.pdf"},
                    document_ids=["DC001"],
                )
            )
        return next(e["result"] for e in events if e["type"] == "result")

    def _task(self, title, refs):
        task = Mock(title=title, evidence_refs=refs)
        task.model_dump.return_value = {"title": title}
        return task

    def test_unknown_reference_is_dropped_not_fatal(self):
        result = self._run([self._task("업무 가", ["E1", "E99"])])

        self.assertEqual(len(result["tasks"]), 1)
        # 아는 번호만 chunk_id 로 되돌아온다.
        self.assertEqual(result["tasks"][0]["evidence_chunk_ids"], ["aaaa-1"])
        self.assertTrue(any("E99" in w for w in result["warnings"]))

    def test_task_without_any_valid_evidence_is_removed(self):
        """근거가 하나도 확인 안 되면 그 업무는 지어낸 것이다."""

        result = self._run([self._task("근거 없는 업무", ["E98", "E99"])])

        self.assertEqual(result["tasks"], [])
        self.assertTrue(any("근거가 하나도" in w for w in result["warnings"]))

    def test_evidence_rows_carry_short_refs(self):
        result = self._run([self._task("업무 가", ["E1"])])

        self.assertEqual([row["ref"] for row in result["evidence"]], ["E1", "E2"])
        # UUID 는 여전히 응답에 남는다 — 화면이 근거를 찾아 보여줘야 한다.
        self.assertEqual(result["evidence"][0]["chunk_id"], "aaaa-1")


class EvidenceBudgetTests(SimpleTestCase):
    """관련 없는 문서가 근거를 잠식하지 못하게 한다.

    팀 문서 전체를 뒤지므로 다른 사업의 문서도 검색에 걸린다. 실제로 감리
    과업지시서가 20자리 중 8자리를 가져가면서 기준 문서의 실제 과업 청크를
    밀어냈고, 그 결과 실행 과업이 한 건도 안 뽑혔다(2026-08-05).
    """

    def _rows(self, doc_id, count, base):
        return [
            {"doc_id": doc_id, "chunk_id": f"{doc_id}-{i}", "retrieval_score": base - i * 0.001}
            for i in range(count)
        ]

    def test_other_documents_cannot_take_more_than_the_reserve(self):
        from services.task_extraction.service import EVIDENCE_LIMIT, SUPPORT_LIMIT, _rank_evidence

        # 다른 문서가 점수로는 전부 앞선 상황을 만든다.
        rows = self._rows("DC002", 30, base=0.9) + self._rows("DC001", 30, base=0.5)

        selected = _rank_evidence(rows, "DC001")

        self.assertEqual(len(selected), EVIDENCE_LIMIT)
        others = [row for row in selected if row["doc_id"] != "DC001"]
        self.assertEqual(len(others), SUPPORT_LIMIT)
        self.assertEqual(len(selected) - len(others), EVIDENCE_LIMIT - SUPPORT_LIMIT)

    def test_primary_fills_everything_when_alone(self):
        from services.task_extraction.service import EVIDENCE_LIMIT, _rank_evidence

        selected = _rank_evidence(self._rows("DC001", 30, base=0.9), "DC001")

        self.assertEqual(len(selected), EVIDENCE_LIMIT)
        self.assertTrue(all(row["doc_id"] == "DC001" for row in selected))

    def test_selection_stays_ordered_by_score(self):
        from services.task_extraction.service import _rank_evidence

        rows = self._rows("DC002", 10, base=0.9) + self._rows("DC001", 10, base=0.8)

        selected = _rank_evidence(rows, "DC001")
        scores = [row["retrieval_score"] for row in selected]

        self.assertEqual(scores, sorted(scores, reverse=True))


class ChunkRevisionScopeTests(SimpleTestCase):
    """청크를 읽는 자리는 **전부** 현재 revision 만 봐야 한다.

    문서가 개정되면 `doc.cur_revision` 이 먼저 바뀌고 새 청크는 워커가 돌아온
    뒤에야 들어온다. 그 사이 `doc_block` 에는 **옛 revision 의 조각이 그대로
    살아 있다** — 재색인이 끝나야 `ingest` 가 지운다.

    2026-08-24 이전에는 `VectorSearchRepository.search` 에만 이 조건이 빠져
    있었다. 그러면 그 구간에서 화면은 `search_ready = false` 를 보고 「본문
    근거를 낼 수 없다」고 말하는데 검색은 **옛 본문을 근거로 돌려준다.**

    아직 실제로 재현되지 않는다 — 수정된 Drive 문서를 다시 받는 경로가 없어
    `cur_revision` 이 바뀔 일이 없다. 변경 감지를 붙이는 순간 드러나므로,
    그 전에 네 자리가 같은 규칙을 쓰는지 여기서 못 박는다.

    SQL 을 문자열로 확인한다. 실제 DB 를 띄우지 않는 테스트라 실행으로는 못
    잡지만, **한 자리만 빠지는** 이 부류는 이름 대조만으로도 잡힌다
    (`test_harness.py` `ToolWiringTests` 와 같은 판단).
    """

    PREDICATE = "b.revision = d.cur_revision"

    @staticmethod
    def _sql_only(func) -> str:
        """docstring 을 걷어낸 본문.

        **이 단계가 없으면 검사가 통과만 한다.** 위 세 함수는 docstring 에서
        이 조건을 설명하고 있어서, SQL 에서 빠져도 `getsource` 는 그 설명을
        보고 「있다」고 답한다(실제로 그렇게 만들었다가 잡았다).
        """

        import inspect

        source = inspect.getsource(func)
        doc = inspect.getdoc(func)
        if doc:
            # `getdoc` 은 들여쓰기를 지운 판이라 원문과 다르다. 첫 줄로 원문
            # 블록의 시작을 찾아 닫는 따옴표까지 잘라낸다.
            head = doc.splitlines()[0]
            start = source.find(head)
            if start >= 0:
                end = source.find('"""', start)
                if end >= 0:
                    source = source[:start] + source[end:]
        return source

    def test_청크를_읽는_모든_질의가_현재_revision_만_본다(self):
        from backend.db import document_pipeline as pipeline

        readers = {
            "_HAS_ACTIVE_CHUNKS": pipeline._HAS_ACTIVE_CHUNKS,
            "VectorSearchRepository.search": self._sql_only(
                pipeline.VectorSearchRepository.search
            ),
            "VectorSearchRepository.table_block_chunks": self._sql_only(
                pipeline.VectorSearchRepository.table_block_chunks
            ),
            "VectorSearchRepository.rank_by_content": self._sql_only(
                pipeline.VectorSearchRepository.rank_by_content
            ),
            "document_outline": self._sql_only(pipeline.document_outline),
        }

        missing = sorted(name for name, sql in readers.items() if self.PREDICATE not in sql)

        self.assertEqual(
            missing,
            [],
            f"현재 revision 으로 거르지 않는 자리가 있다: {missing}. "
            "재색인 중인 문서의 옛 본문이 근거로 나간다.",
        )


class UploadWorkerFormatParityTests(SimpleTestCase):
    """올릴 수 있는 형식은 **워커가 읽을 수 있어야 한다.**

    두 목록이 따로 자라면 사용자는 올릴 수는 있는데 색인만 실패하는 파일을 갖게
    된다. 화면은 「본문 색인 실패」와 사유를 보여 주지만, 애초에 받지 말았어야
    할 파일이라 사람이 할 수 있는 일이 없다.

    2026-08-24 에 실제로 그 상태였다 — 요약 단계를 없애면서 txt·md 의 근거
    (「워커는 못 읽어도 요약은 우리 CPU 가 만든다」)가 사라졌는데 업로드 목록에는
    그대로 남아 있었다. 워커에 MD 백엔드를 붙여 맞췄다.
    """

    def test_올릴_수_있는_형식은_워커가_전부_읽는다(self):
        from backend.services import storage
        from runpod_worker.pipeline import SUPPORTED_MIME_TYPES

        uploadable = set(storage._UPLOAD_TYPES.values())
        readable = set(SUPPORTED_MIME_TYPES)

        self.assertEqual(
            sorted(uploadable - readable),
            [],
            "올릴 수는 있는데 워커가 못 읽는 형식이 있다. "
            "업로드에서 빼거나 워커에 백엔드를 붙여야 한다.",
        )

    def test_평문은_마크다운_백엔드로_보낸다(self):
        """docling 2.117 의 `InputFormat` 에는 평문 형식이 아예 없다(휠 실측).
        평문은 유효한 마크다운이라 그쪽으로 보낸다 — 별도 경로를 만들면 청킹과
        블록 생성이 두 벌이 된다."""

        from runpod_worker.pipeline import SUPPORTED_MIME_TYPES

        self.assertEqual(SUPPORTED_MIME_TYPES["text/plain"], ".md")
        self.assertEqual(SUPPORTED_MIME_TYPES["text/markdown"], ".md")
