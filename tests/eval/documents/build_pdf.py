"""평가용 문서 HTML을 PDF로 굽는다.

Chrome 헤드리스의 `--print-to-pdf` 를 쓴다. 파이썬 PDF 라이브러리를 새로 깔지
않으려는 것이 첫째 이유이고, 한글 조판(줄바꿈·자간·표 넘김)을 브라우저가
가장 정확하게 하기 때문이 둘째다. 결과는 텍스트가 살아 있는 PDF라 워커의
docling 파싱이 OCR 없이 본문을 읽는다.

실행:

    .venv/Scripts/python.exe tests/eval/documents/build_pdf.py

`pdf/` 아래에 Drive 에 올릴 이름 그대로 나온다. 파일 이름이 곧 화면에 보이는
문서 이름이므로 번호 접두사를 떼고 사람이 읽는 이름을 쓴다.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "pdf"

#: (원본 HTML, 나갈 PDF 이름). 순서는 문서 번호 순이다.
DOCUMENTS = [
    ("01_과업지시서.html", "한빛몰_주문정산_고도화_과업지시서.pdf"),
    ("02_요구사항정의서.html", "한빛몰_주문정산_요구사항정의서.pdf"),
    ("03_인력운영계획서.html", "한빛몰_주문정산_투입인력_운영계획서.pdf"),
    ("04_WBS_마일스톤.html", "한빛몰_주문정산_WBS_마일스톤.pdf"),
    ("05_기술검토회의록.html", "한빛몰_주문정산_기술검토회의록.pdf"),
    ("06_타사업_그룹웨어_유지보수.html", "한빛리테일_사내그룹웨어_유지보수_과업지시서.pdf"),
    ("07_그룹웨어_SLA합의서.html", "한빛리테일_사내그룹웨어_SLA_부속합의서.pdf"),
    ("08_그룹웨어_개선요청_접수내역.html", "한빛리테일_사내그룹웨어_개선요청_접수내역.pdf"),
]

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_browser() -> str:
    for path in CHROME_CANDIDATES:
        if Path(path).exists():
            return path
    for name in ("chrome", "google-chrome", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit("Chrome 또는 Edge 를 찾지 못했다. CHROME_CANDIDATES 에 경로를 더할 것.")


def main() -> int:
    browser = find_browser()
    OUT.mkdir(exist_ok=True)
    failed = []

    with tempfile.TemporaryDirectory() as profile:
        for source, target in DOCUMENTS:
            src = HERE / source
            if not src.exists():
                failed.append(f"{source}: 원본이 없다")
                continue
            dst = OUT / target
            subprocess.run(
                [
                    browser,
                    "--headless=new",
                    "--disable-gpu",
                    f"--user-data-dir={profile}",
                    # 브라우저가 붙이는 URL·날짜 머리말/꼬리말을 뺀다. 파싱에는
                    # 페이지마다 반복되는 잡음이라 청크에 섞이면 검색을 흐린다.
                    "--no-pdf-header-footer",
                    # CSS 를 다 읽기 전에 인쇄해 서식이 빠지는 것을 막는다.
                    "--virtual-time-budget=4000",
                    f"--print-to-pdf={dst}",
                    src.as_uri(),
                ],
                check=False,
                capture_output=True,
            )
            # Chrome 은 실패해도 0 을 돌려줄 때가 있다. 결과 파일로 판정한다.
            if not dst.exists() or dst.stat().st_size < 5_000:
                failed.append(f"{source}: PDF 가 안 나왔거나 너무 작다")
                continue
            print(f"  {target}  {dst.stat().st_size // 1024}KB")

    if failed:
        print("\n실패:", file=sys.stderr)
        for line in failed:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(f"\n{len(DOCUMENTS)}건 완료 → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
