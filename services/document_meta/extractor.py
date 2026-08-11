"""원문에서 텍스트만 뽑는다 — **CPU 로, GPU 없이.**

`runpod_worker` 의 docling 파이프라인과 목적이 다르다. 그쪽은 구조(블록·표·
제목 경로)를 보존해 청킹까지 하는 무거운 경로고, 여기는 "이 문서가 무엇에
대한 것인가"를 요약할 만큼의 평문만 있으면 된다. 그래서 팀 문서 전부에
돌릴 수 있다 — coarse 검색이 서려면 미처리 문서에도 메타가 있어야 한다.

**뽑지 못한 것을 뽑은 척하지 않는다.** 텍스트 레이어가 없는 스캔 PDF 는
FAILED 고, 우리가 다룰 수 없는 형식은 UNSUPPORTED 다. 둘은 다른 상태다 —
전자는 OCR 을 붙이면 되고 후자는 파서가 없다.
"""

from __future__ import annotations

from dataclasses import dataclass

#: 추출 상태. `doc_meta.extract_status` 에 그대로 들어간다.
OK = "OK"
FAILED = "FAILED"
UNSUPPORTED = "UNSUPPORTED"

#: 이만큼도 안 나오면 텍스트 레이어가 없다고 본다.
#:
#: 스캔 PDF 도 페이지마다 머리말·쪽번호 몇 글자는 뽑힌다. 0 자를 기준으로 하면
#: 그런 문서가 OK 로 남아 "내용이 거의 없는 문서"라는 요약을 만들어 낸다.
MIN_TEXT_CHARS = 200

#: 요약에 넘길 상한. 앞부분에 개요·사업범위가 들어 있어서 여기까지면 문서가
#: 무엇인지 판단하는 데 충분하고, 넘기면 요약 한 번 값이 그만큼 는다.
SUMMARY_INPUT_MAX_CHARS = 12000

#: 우리가 CPU 로 평문을 뽑을 수 있는 형식.
#:
#: docx·pptx·xlsx 는 여기 없다. zip 안의 XML 이라 전용 파서가 필요한데,
#: 그것들은 이미 docling 경로가 다룬다 — 메타만 만들자고 파서를 하나 더 들이는
#: 것보다 UNSUPPORTED 로 두고 처리된 뒤 chunk 에서 만드는 편이 낫다.
TEXT_MIMES = frozenset({"text/plain", "text/markdown", "text/csv"})
PDF_MIME = "application/pdf"


@dataclass(frozen=True)
class Extraction:
    status: str
    text: str = ""
    #: 사람이 읽을 실패 사유. OK 면 비어 있다.
    detail: str = ""


def extract(*, content: bytes, mime_type: str | None, file_name: str | None = None) -> Extraction:
    """원문 바이트에서 평문을 뽑는다. 예외를 던지지 않고 상태로 답한다.

    문서 하나가 이상하다고 파이프라인 전체가 멈추면 안 된다 — 팀 문서 전부에
    돌리는 일이라 한 건의 실패는 그 한 건으로 끝나야 한다.
    """

    mime = (mime_type or "").split(";")[0].strip().lower()
    name = (file_name or "").lower()

    if name.endswith((".hwp", ".hwpx")) or "hwp" in mime:
        # 파서가 없다. 붙이면 OK 가 될 수 있어서 FAILED 와 구분한다.
        return Extraction(UNSUPPORTED, detail="hwp 는 아직 다룰 수 있는 파서가 없습니다.")

    if mime in TEXT_MIMES or name.endswith((".txt", ".md", ".csv")):
        text = content.decode("utf-8", errors="replace").strip()
        if len(text) < MIN_TEXT_CHARS:
            return Extraction(FAILED, detail="본문이 너무 짧아 요약할 내용이 없습니다.")
        return Extraction(OK, text=text)

    if mime == PDF_MIME or name.endswith(".pdf"):
        return _from_pdf(content)

    return Extraction(UNSUPPORTED, detail=f"CPU 텍스트 추출을 지원하지 않는 형식입니다: {mime or '알 수 없음'}")


def _from_pdf(content: bytes) -> Extraction:
    from io import BytesIO

    from pypdf import PdfReader
    # `PyPdfError` 가 pypdf 예외의 기반 클래스다(`PdfError` 라는 이름은 없다).
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            # 빈 암호로 열리는 문서가 흔하다(보기 제한만 걸어 둔 경우).
            try:
                reader.decrypt("")
            except Exception:  # noqa: BLE001 - 어떤 방식이든 못 열면 결론은 같다
                return Extraction(FAILED, detail="암호가 걸린 PDF 라 열 수 없습니다.")
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001 - 한 페이지가 깨져도 나머지는 쓴다
                continue
    except (PyPdfError, ValueError, OSError) as exc:
        return Extraction(FAILED, detail=f"PDF 를 읽지 못했습니다: {exc.__class__.__name__}")

    text = "\n".join(pages).strip()
    if len(text) < MIN_TEXT_CHARS:
        # 스캔본이다. OCR 을 붙이면 되므로 UNSUPPORTED 가 아니라 FAILED 다.
        return Extraction(FAILED, detail="텍스트 레이어가 없는 PDF 입니다(스캔본으로 보입니다).")
    if _is_garbled(text):
        return Extraction(
            FAILED, detail="글자가 깨져서 추출됐습니다(폰트 매핑이 없는 PDF)."
        )
    return Extraction(OK, text=text)


#: 한글 최빈 글자가 이 비율을 넘으면 깨진 것으로 본다.
#:
#: 실측(2026-08-11): 정상 PDF 0.031, 폰트 CMap 이 없는 PDF 0.736 — 같은 글자
#: 하나가 5,972/8,119 를 차지했다("SK 네네네네 Family AI 네네"). 두 값 사이가
#: 넓어서 경계를 어디에 둬도 되지만, 표가 많은 문서가 특정 글자에 몰릴 수 있어
#: 여유를 둔다.
GARBLED_MAX_CHAR_RATIO = 0.30

#: 이만큼 한글이 있어야 비율을 따진다. 영문·숫자 문서를 깨졌다고 하면 안 된다.
GARBLED_MIN_HANGUL = 100


def _is_garbled(text: str) -> bool:
    """글자는 나왔는데 뜻이 없는 경우.

    글자 수만 보면 통과한다 — 실제로 18,961 자가 나왔고 전부 같은 글자였다.
    이대로 요약하면 그럴듯한 헛소리가 만들어지고, 그 요약의 임베딩이 coarse
    검색에 들어가 관계없는 질의에 걸린다. 뽑지 못한 것은 못 뽑았다고 한다.
    """

    from collections import Counter

    hangul = [char for char in text if "가" <= char <= "힣"]
    if len(hangul) < GARBLED_MIN_HANGUL:
        return False
    most_common = Counter(hangul).most_common(1)[0][1]
    return most_common / len(hangul) > GARBLED_MAX_CHAR_RATIO


def for_summary(text: str) -> str:
    """요약 모델에 넘길 만큼만 자른다."""

    return text[:SUMMARY_INPUT_MAX_CHARS]
