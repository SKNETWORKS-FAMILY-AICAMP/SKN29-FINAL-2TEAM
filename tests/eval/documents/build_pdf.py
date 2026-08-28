"""평가용 문서를 PDF로 굽는다.

원본은 두 갈래다.

1. `*.html` — 손으로 쓴 초기 8종. `DOCUMENTS` 표가 이름을 정한다.
2. `specs/*.py` — 명세(dict)로 쓴 나머지. `render.py` 가 HTML 로 만든 뒤 같은
   경로를 탄다. 90여 종을 손으로 HTML 을 쓰면 **문서 모양이 균일해지고**, 모양이
   같으면 임베딩 공간에서 서로 가까워져 노이즈가 노이즈 구실을 못 한다.

Chrome 헤드리스의 `--print-to-pdf` 를 쓴다. 파이썬 PDF 라이브러리를 새로 깔지
않으려는 것이 첫째 이유이고, 한글 조판(줄바꿈·자간·표 넘김)을 브라우저가 가장
정확하게 하기 때문이 둘째다. 결과는 텍스트가 살아 있는 PDF라 워커의 docling
파싱이 OCR 없이 본문을 읽는다.

실행:

    .venv/Scripts/python.exe tests/eval/documents/build_pdf.py
    .venv/Scripts/python.exe tests/eval/documents/build_pdf.py --only p03

`pdf/` 아래에 Drive 에 올릴 이름 그대로 나온다. 파일 이름이 곧 화면에 보이는
문서 이름이므로 번호 접두사를 떼고 사람이 읽는 이름을 쓴다.
"""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPECS = HERE / "specs"
OUT = HERE / "pdf"

sys.path.insert(0, str(HERE))
from render import render  # noqa: E402

#: 문서를 담을 폴더. Drive 에도 이 구조 그대로 올린다 — 실제 팀 드라이브가
#: 그렇게 생겼고, 폴더 스캔 깊이(`team_folder.max_depth`)가 하위까지 훑는지도
#: 함께 확인된다. 폴더 이름은 색인에 안 들어가므로 정답지와는 무관하다.
FOLDERS = {
    "p03_wms": "P3_하나로유통_김천WMS_재구축",
    "p04_openbanking": "P4_케이뱅크플러스_오픈뱅킹API",
    "p05_emr": "P5_메디컬링크_EMR_클라우드전환",
    "p06_pdm": "P6_정우기계_예지보전플랫폼",
    "p07_transit": "P7_시티모빌리티_교통카드정산",
    "p08_lms": "P8_에듀랩_차세대LMS",
    "noise_a": "00_배경문서",
    "noise_b": "00_배경문서",
    "noise_c": "00_배경문서",
}

#: 손으로 쓴 것은 원본 이름 앞자리로 가른다.
HAND_FOLDER = {
    "hard/": "P1_한빛몰_주문정산_고도화",
    "01": "P1_한빛몰_주문정산_고도화", "02": "P1_한빛몰_주문정산_고도화",
    "03": "P1_한빛몰_주문정산_고도화", "04": "P1_한빛몰_주문정산_고도화",
    "05": "P1_한빛몰_주문정산_고도화",
    "06": "P2_한빛리테일_사내그룹웨어", "07": "P2_한빛리테일_사내그룹웨어",
    "08": "P2_한빛리테일_사내그룹웨어",
}


#: 손으로 쓴 HTML. (원본, 나갈 PDF 이름)
DOCUMENTS = [
    ("01_과업지시서.html", "한빛몰_주문정산_고도화_과업지시서.pdf"),
    ("02_요구사항정의서.html", "한빛몰_주문정산_요구사항정의서.pdf"),
    ("03_인력운영계획서.html", "한빛몰_주문정산_투입인력_운영계획서.pdf"),
    ("04_WBS_마일스톤.html", "한빛몰_주문정산_WBS_마일스톤.pdf"),
    ("05_기술검토회의록.html", "한빛몰_주문정산_기술검토회의록.pdf"),
    ("06_타사업_그룹웨어_유지보수.html", "한빛리테일_사내그룹웨어_유지보수_과업지시서.pdf"),
    ("07_그룹웨어_SLA합의서.html", "한빛리테일_사내그룹웨어_SLA_부속합의서.pdf"),
    ("08_그룹웨어_개선요청_접수내역.html", "한빛리테일_사내그룹웨어_개선요청_접수내역.pdf"),
    # 파싱 난이도를 일부러 올린 문서(`hard/hard.css`) — 제목을 개조식 기호로만
    # 구분하고 글자 크기 차이를 없앴다. 서식 네 벌이 「제목 크기가 다르면」을
    # 묻는다면 이쪽은 「차이가 아예 없으면」을 묻는다.
    ("hard/H01_품의서.html", "한빛리테일_주문정산_고도화_추진품의서.pdf"),
]

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def _hand_folder(source: str) -> str:
    for prefix, folder in HAND_FOLDER.items():
        if source.startswith(prefix):
            return folder
    raise KeyError(f"폴더를 못 정했다: {source}")


def find_browser() -> str:
    for path in CHROME_CANDIDATES:
        if Path(path).exists():
            return path
    for name in ("chrome", "google-chrome", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit("Chrome 또는 Edge 를 찾지 못했다. CHROME_CANDIDATES 에 경로를 더할 것.")


def load_specs() -> list[tuple[str, str, str]]:
    """`specs/*.py` 를 읽어 HTML 로 펼치고 (원본, 폴더, 나갈 이름) 목록을 돌려준다."""
    pairs: list[tuple[str, str, str]] = []
    for path in sorted(SPECS.glob("*.py")):
        if path.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for doc in getattr(module, "DOCUMENTS", []):
            (HERE / doc["source"]).write_text(render(doc), encoding="utf-8")
            pairs.append((doc["source"], FOLDERS.get(path.stem, "00_배경문서"), doc["target"]))
    return pairs


def to_pdf(browser: str, profile: str, source: Path, target: Path) -> str | None:
    subprocess.run(
        [
            browser,
            "--headless=new",
            "--disable-gpu",
            f"--user-data-dir={profile}",
            # 브라우저가 붙이는 URL·날짜 머리말/꼬리말을 뺀다. 파싱에는 페이지마다
            # 반복되는 잡음이라 청크에 섞이면 검색을 흐린다.
            "--no-pdf-header-footer",
            # CSS 를 다 읽기 전에 인쇄해 서식이 빠지는 것을 막는다.
            "--virtual-time-budget=4000",
            f"--print-to-pdf={target}",
            source.as_uri(),
        ],
        check=False,
        capture_output=True,
    )
    # Chrome 은 실패해도 0 을 돌려줄 때가 있다. 결과 파일로 판정한다.
    if not target.exists() or target.stat().st_size < 5_000:
        return "PDF 가 안 나왔거나 너무 작다"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="원본 이름에 이 문자열이 든 것만 굽는다 (예: p03)")
    args = parser.parse_args()

    browser = find_browser()
    OUT.mkdir(exist_ok=True)

    pairs = [(src, _hand_folder(src), tgt) for src, tgt in DOCUMENTS] + load_specs()
    if args.only:
        pairs = [p for p in pairs if args.only in p[0]]
    if not pairs:
        raise SystemExit("구울 문서가 없다.")

    failed: list[str] = []
    with tempfile.TemporaryDirectory() as profile:
        for source_name, folder, target_name in pairs:
            source = HERE / source_name
            if not source.exists():
                failed.append(f"{source_name}: 원본이 없다")
                continue
            (OUT / folder).mkdir(parents=True, exist_ok=True)
            target = OUT / folder / target_name
            problem = to_pdf(browser, profile, source, target)
            if problem:
                failed.append(f"{source_name}: {problem}")
                continue
            print(f"  {folder}/{target_name}  {target.stat().st_size // 1024}KB")

    if failed:
        print("\n실패:", file=sys.stderr)
        for line in failed:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(f"\n{len(pairs)}건 완료 → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
