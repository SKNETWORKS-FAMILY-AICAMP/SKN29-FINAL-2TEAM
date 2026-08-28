"""정답지와 문서가 서로 맞는지 **DB 없이** 검사한다.

문서를 여럿이 나눠 쓰기 때문에 필요하다. 저자들은 서로의 문서를 보지 못하므로
같은 문구를 앵커로 고르는 사고가 난다. 앵커가 두 문서에 있으면 변별력이 0 이라
그 질의는 무엇을 재는지 알 수 없어진다 — 그런데 **오류가 나지 않아서** 채점
결과만 보면 모른다.

`retrieval_eval.py` 의 preflight 도 같은 것을 보지만 그쪽은 색인된 청크를 본다.
이 검사는 **올리기 전에** 원본에서 잡는다. 수집에 30분이 걸리므로 그 전에
거르는 편이 싸다.

실행:

    .venv/Scripts/python.exe tests/eval/validate.py
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DOCS = HERE / "documents"
SPECS = DOCS / "specs"
GOLDEN = HERE / "golden"

sys.path.insert(0, str(DOCS))
from build_pdf import DOCUMENTS as HANDWRITTEN  # noqa: E402
from render import render  # noqa: E402


def flat(text: str) -> str:
    """공백을 전부 지운다. 채점과 같은 규칙이어야 한다."""
    return re.sub(r"\s+", "", text or "")


def strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def collect() -> tuple[dict[str, str], list[str]]:
    """문서 이름 → 본문(공백 제거). 두 번째 값은 발견한 문제."""
    bodies: dict[str, str] = {}
    problems: list[str] = []
    sources: dict[str, str] = {}

    for source, target in HANDWRITTEN:
        path = DOCS / source
        if not path.exists():
            problems.append(f"손으로 쓴 원본이 없다: {source}")
            continue
        bodies[target] = flat(strip_tags(path.read_text(encoding="utf-8")))
        sources[source] = target

    for path in sorted(SPECS.glob("*.py")):
        if path.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"명세를 읽지 못했다: {path.name} ({exc})")
            continue
        docs = getattr(module, "DOCUMENTS", None)
        if not docs:
            problems.append(f"DOCUMENTS 가 비었다: {path.name}")
            continue
        for doc in docs:
            for key in ("source", "target", "title", "sections"):
                if key not in doc:
                    problems.append(f"{path.name}: '{key}' 가 없는 문서가 있다")
                    break
            else:
                if doc["target"] in bodies:
                    problems.append(f"PDF 이름이 겹친다: {doc['target']} ({path.name})")
                if doc["source"] in sources:
                    problems.append(f"원본 이름이 겹친다: {doc['source']} ({path.name})")
                sources[doc["source"]] = doc["target"]
                try:
                    bodies[doc["target"]] = flat(strip_tags(render(doc)))
                except Exception as exc:  # noqa: BLE001
                    problems.append(f"조판 실패: {doc['target']} ({exc})")
    return bodies, problems



#: 앵커 후보를 뽑을 때 쓰는 조각. 숫자가 든 짧은 구절이 앵커로 좋다 —
#: 서술문은 길어서 청킹 경계에 잘리기 쉽고, 숫자 없는 구절은 상투구일 확률이 높다.
CANDIDATE = re.compile(r"[가-힣A-Za-z%·\.\,\(\)]{0,14}[0-9][0-9,\.]*\s*[가-힣A-Za-z%]{0,10}")


def suggest(bodies: dict[str, str], needle: str, limit: int = 25) -> None:
    """`needle` 이 이름에 든 문서에서, **그 문서에만 있는** 숫자 구절을 뽑는다.

    앵커가 겹쳐 못 쓰게 됐을 때 갈아 끼울 후보를 사람이 눈으로 고르라고 주는 것이다.
    """
    targets = [n for n in bodies if needle in n]
    if not targets:
        print(f"그런 문서가 없다: {needle}")
        return
    for name in targets:
        raw = bodies[name]
        uniq = []
        for m in dict.fromkeys(CANDIDATE.findall(raw)):
            token = m.strip()
            if len(token) < 6:
                continue
            if sum(1 for other, body in bodies.items() if token in body) == 1:
                uniq.append(token)
        print(f"\n{name}  — 이 문서에만 있는 구절 {len(uniq)}개")
        for token in uniq[:limit]:
            print(f"    {token}")


def main() -> int:
    bodies, problems = collect()

    if len(sys.argv) > 2 and sys.argv[1] == "--suggest":
        suggest(bodies, sys.argv[2])
        return 0


    queries: list[dict] = []
    seen: dict[str, str] = {}
    for path in [GOLDEN / "retrieval.json", *sorted(GOLDEN.glob("queries_*.json"))]:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            problems.append(f"JSON 을 읽지 못했다: {path.name} ({exc})")
            continue
        for q in data.get("queries", []):
            if q["id"] in seen:
                problems.append(f"질의 id 가 겹친다: {q['id']} ({path.name} · {seen[q['id']]})")
                continue
            seen[q["id"]] = path.name
            queries.append(q)

    missing, split, ambiguous = [], [], []
    for q in queries:
        want = q["expect"]["document"]
        anchor = flat(q["expect"]["anchor"])
        if want not in bodies:
            missing.append(f"{q['id']}: 없는 문서를 가리킨다 — {want}")
            continue
        if anchor not in bodies[want]:
            split.append(f"{q['id']}: 앵커가 그 문서에 없다 — 「{q['expect']['anchor']}」 ({want})")
            continue
        others = [name for name, body in bodies.items() if name != want and anchor in body]
        if others:
            ambiguous.append(f"{q['id']}: 앵커가 여러 문서에 있다 — 「{q['expect']['anchor']}」 → {others}")

    print(f"문서 {len(bodies)}종 · 질의 {len(queries)}개\n")
    for title, items in (
        ("구조 문제", problems),
        ("정답 문서가 없다", missing),
        ("앵커가 본문에 없다", split),
        ("앵커가 여러 문서에 있다 (변별력 0)", ambiguous),
    ):
        if items:
            print(f"⚠ {title} {len(items)}건")
            for line in items[:20]:
                print(f"    {line}")
            if len(items) > 20:
                print(f"    … 그리고 {len(items) - 20}건 더")
            print()

    total = len(problems) + len(missing) + len(split) + len(ambiguous)
    if total == 0:
        print("문제 없음. 올려도 된다.")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
