"""`tool_completed` 가 실어 보내는 `produced_file` 의 계약.

여기서 보는 것은 하나다 — **「본 문서」와 「만든 파일」이 섞이지 않는가.**
읽기 도구 결과에도 `doc_id` 가 잔뜩 들어 있어서, 그것으로 판단하면 문서를
검색만 해도 받기 단추가 생긴다.
"""

import json

from django.test import SimpleTestCase

from services.agent_runtime.events import _produced_file, _retrieved_doc_ids


class ProducedFileTests(SimpleTestCase):
    def test_file_키를_담은_결과에서만_뽑는다(self):
        content = json.dumps(
            {"file": {"doc_id": "DC001", "file_name": "표.xlsx", "mime_type": "x/y"}, "rows": 3},
            ensure_ascii=False,
        )

        self.assertEqual(
            _produced_file(content),
            {"doc_id": "DC001", "file_name": "표.xlsx", "mime_type": "x/y"},
        )

    def test_검색_결과의_doc_id_는_만든_파일이_아니다(self):
        """`document_search` 결과다. `doc_id` 가 여럿 있어도 받기 단추는 없어야 한다."""

        content = json.dumps(
            {
                "evidence": [{"doc_id": "DC010", "quote": "..."}, {"doc_id": "DC011", "quote": "..."}],
                "not_indexed": [{"doc_id": "DC012"}],
            },
            ensure_ascii=False,
        )

        self.assertIsNone(_produced_file(content))
        # 같은 값에서 감사용 doc_id 는 여전히 뽑힌다 — 두 값은 서로 다른 질문이다.
        self.assertEqual(_retrieved_doc_ids(content), ["DC010", "DC011", "DC012"])

    def test_평문을_돌려주는_도구는_조용히_없음이다(self):
        self.assertIsNone(_produced_file("등록했습니다."))
        self.assertIsNone(_produced_file(None))
        self.assertIsNone(_produced_file('{"file": "문자열이라 파일이 아니다"}'))

    def test_모양이_덜_갖춰진_file_은_받지_않는다(self):
        """`doc_id` 나 `file_name` 이 없으면 카드를 그릴 수 없다."""

        self.assertIsNone(_produced_file(json.dumps({"file": {"doc_id": "DC001"}})))
        self.assertIsNone(_produced_file(json.dumps({"file": {"file_name": "x.xlsx"}})))

    def test_mime_이_없으면_비운다(self):
        """지어내지 않는다 — 화면은 이름과 아이콘만으로도 그릴 수 있다."""

        got = _produced_file(json.dumps({"file": {"doc_id": "DC001", "file_name": "x.bin"}}))

        self.assertEqual(got, {"doc_id": "DC001", "file_name": "x.bin", "mime_type": None})

    def test_실제_도구_결과에서_뽑힌다(self):
        """`registry._file_ref()` 가 만든 모양과 여기가 읽는 모양이 같아야 한다."""

        from services.harness.registry import _file_ref

        content = json.dumps({"file": _file_ref("DC009", "보고서.docx", "a/b")}, ensure_ascii=False)

        self.assertEqual(
            _produced_file(content),
            {"doc_id": "DC009", "file_name": "보고서.docx", "mime_type": "a/b"},
        )
