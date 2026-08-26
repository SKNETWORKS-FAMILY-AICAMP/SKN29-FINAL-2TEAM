"""글 한 편을 docx 바이트로 굽는다.

`document_create` 도구가 부른다. 본문은 **모델이 쓴 마크다운**인데, 전부를
해석하지 않는다 — 화면 쪽 `AnswerText.tsx` 와 **같은 판단**이다:

    모델이 실제로 쓰는 문법은 몇 개뿐이고(제목 · 목록 · 굵게 · 문단),
    그것만 그리면 의존성이 0이다.

그래서 마크다운 파서를 넣지 않고 줄 단위로 읽는다. 처리하는 것은 넷이다 —
`#`~`###` 제목, `- `/`* ` 목록, `1. ` 번호 목록, `**굵게**`. 나머지는 **글자
그대로** 둔다. 잘못 그리는 것보다 낫고, 그 판단은 화면이 이미 같은 이유로
내렸다.

**표는 안 만든다.** 표가 필요하면 `table_export` 가 xlsx 로 낸다 — 워드 표를
여기서 또 만들면 같은 것을 두 곳에서 다르게 그리게 된다.
"""

from __future__ import annotations

import re
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

#: `**굵게**` 를 조각으로 가른다. 화면의 `inline()` 이 쓰는 것과 같은 규칙이다.
_BOLD = re.compile(r"(\*\*[^*]+\*\*)")

#: `1. ` · `1) ` 로 시작하는 번호 목록.
_ORDERED = re.compile(r"^\s*\d+[.)]\s+")

#: 제어문자. 워드가 XML 에 못 담는 값이 본문에 섞여 오면 파일이 열리지 않는다.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _write_inline(paragraph, text: str) -> None:
    """`**굵게**` 만 살려서 문단에 적는다. 나머지는 글자 그대로."""

    for part in _BOLD.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            paragraph.add_run(part[2:-2]).bold = True
        else:
            paragraph.add_run(part)


def build_docx(*, title: str, body: str) -> bytes:
    """제목과 본문(마크다운)으로 docx 를 만들어 바이트로 돌려준다."""

    document = Document()

    # 기본 글꼴 크기만 손댄다. 워드 기본값(11pt)이 한글 문서로는 촘촘하다.
    normal = document.styles["Normal"]
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)

    heading = document.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = heading.add_run(_CONTROL.sub("", title).strip() or "제목 없음")
    run.bold = True
    run.font.size = Pt(18)

    for raw in _CONTROL.sub("", body or "").split("\n"):
        line = raw.rstrip()
        stripped = line.strip()

        # 빈 줄은 문단을 나눈다. 빈 문단을 넣지는 않는다 — 워드에서 여백이
        # 두 배로 벌어진다(문단 간격이 이미 있다).
        if not stripped:
            continue

        if stripped.startswith("### "):
            document.add_heading(stripped[4:].strip(), level=3)
        elif stripped.startswith("## "):
            document.add_heading(stripped[3:].strip(), level=2)
        elif stripped.startswith("# "):
            document.add_heading(stripped[2:].strip(), level=1)
        elif stripped.startswith(("- ", "* ")):
            _write_inline(document.add_paragraph(style="List Bullet"), stripped[2:].strip())
        elif _ORDERED.match(stripped):
            _write_inline(
                document.add_paragraph(style="List Number"), _ORDERED.sub("", stripped)
            )
        else:
            _write_inline(document.add_paragraph(), stripped)

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
