"""`table_export` 가 굽는 xlsx 의 계약.

여기서 보는 것은 **모델이 준 값을 그대로 믿지 않는다**는 한 가지다 —
수식으로 해석될 글자, 열 수가 안 맞는 행, 엑셀이 거절하는 시트 이름.
"""

from io import BytesIO

from django.test import SimpleTestCase
from openpyxl import load_workbook

from services.document_export import build_xlsx


def _sheet(data: bytes):
    return load_workbook(BytesIO(data)).active


class BuildXlsxTests(SimpleTestCase):
    def test_머리글과_행을_그대로_적는다(self):
        sheet = _sheet(
            build_xlsx(
                title="업무 목록",
                columns=["제목", "담당", "공수"],
                rows=[["로그인 구현", "김준억", 16], ["정산 배치", "원빈", 8]],
            )
        )

        self.assertEqual(sheet.title, "업무 목록")
        self.assertEqual([c.value for c in sheet[1]], ["제목", "담당", "공수"])
        self.assertEqual([c.value for c in sheet[2]], ["로그인 구현", "김준억", 16])
        # 숫자는 숫자로 남아야 한다 — 문자열이면 합계도 정렬도 안 된다.
        self.assertIsInstance(sheet.cell(row=2, column=3).value, int)

    def test_수식으로_보이는_글자를_실행하지_않는다(self):
        """문서에 적혀 있던 `=...` 이 셀 수식이 되면 파일을 여는 사람 쪽에서 돈다."""

        sheet = _sheet(
            build_xlsx(
                title="근거",
                columns=["=HYPERLINK(\"http://x\")"],
                rows=[["=1+1"], ["+1"], ["@SUM(A1)"], ["-2"]],
            )
        )

        for row in range(1, 5 + 1):
            cell = sheet.cell(row=row, column=1)
            self.assertEqual(cell.data_type, "s", f"{row}행이 글자가 아니다: {cell.value!r}")
        # 값 자체는 안 바꾼다. 보이는 글자가 원문과 달라지면 그것도 왜곡이다.
        self.assertEqual(sheet.cell(row=2, column=1).value, "=1+1")

    def test_열_수가_안_맞는_행을_머리글에_맞춘다(self):
        sheet = _sheet(
            build_xlsx(
                title="t",
                columns=["A", "B", "C"],
                rows=[["1"], ["1", "2", "3", "4"]],
            )
        )

        self.assertEqual([c.value for c in sheet[2]], ["1", None, None])
        self.assertEqual([c.value for c in sheet[3]], ["1", "2", "3"])

    def test_행이_없어도_머리글만_있는_파일이_나온다(self):
        sheet = _sheet(build_xlsx(title="t", columns=["A", "B"], rows=[]))

        self.assertEqual(sheet.max_row, 1)
        self.assertEqual([c.value for c in sheet[1]], ["A", "B"])

    def test_엑셀이_거절하는_시트_이름을_고친다(self):
        # 금지 글자(`[]:*?/\`)와 31자 상한. 어기면 파일이 아예 안 열린다.
        long_title = "가" * 40
        self.assertEqual(len(_sheet(build_xlsx(title=long_title, columns=["A"], rows=[])).title), 31)
        self.assertEqual(_sheet(build_xlsx(title="a/b:c", columns=["A"], rows=[])).title, "abc")
        # 금지 글자만 있던 제목은 빈 이름이 되는데, 엑셀은 그것도 거절한다.
        self.assertEqual(_sheet(build_xlsx(title="///", columns=["A"], rows=[])).title, "표")

    def test_참거짓과_빈값을_사람이_읽는_모양으로_적는다(self):
        sheet = _sheet(
            build_xlsx(title="t", columns=["A", "B", "C"], rows=[[True, False, None]])
        )

        # bool 은 int 의 하위형이라 순서를 안 지키면 1/0 으로 들어간다.
        self.assertEqual([c.value for c in sheet[2]], ["예", "아니오", None])
