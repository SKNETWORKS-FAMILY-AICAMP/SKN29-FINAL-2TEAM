"""업무 추출 sLLM 학습 데이터셋 생성.

**무엇을 배우게 하는가.** 지금 `services/task_extraction` 이 OpenAI 로 하는 일 —
근거 청크를 주면 `ExtractionResult` 스키마에 맞는 업무 JSON 을 뱉는 것 — 을
작은 모델이 하게 만든다. 기획서 v2 의 「보안 sLLM」이 노린 지점이 이것이다:
사내 문서를 외부 API 로 보내지 않고 업무를 뽑는다.

**왜 이 과제인가.** 채점이 자동으로 된다. 스키마 준수 여부는 pydantic 이
판정하고, 필드 일치는 문자열 비교로 잰다. 「좋아진 것 같다」가 아니라 숫자가
나온다.

**라벨은 증류(distillation)로 만든다.** 사람이 15만 자를 읽고 업무를 뽑을 수
없으므로, 이미 운영에 쓰는 교사 모델의 출력을 정답으로 삼는다. 표준 기법이고
보고서에도 그대로 적는다 — 교사가 틀리면 학생도 틀린다는 한계까지 함께.

**분할은 문서 단위다.** 청크 단위로 섞으면 같은 문서의 다른 문단이 학습·평가에
동시에 들어가 점수가 부풀려진다. 평가 문서는 학습에서 통째로 뺀다.

사용법:
    python ml/sllm/build_dataset.py                 # 전체
    python ml/sllm/build_dataset.py --limit 5       # 표본만(비용 확인용)
    python ml/sllm/build_dataset.py --dry-run       # 교사 호출 없이 청크만
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

SOURCE_DIR = REPO / "docs" / "참고자료" / "개발_기획서_샘플"
OUT_DIR = Path(__file__).resolve().parent / "data"

#: 평가 전용 문서. **학습에 한 글자도 들어가지 않는다.**
#: 처음에는 EU 스펙(7만 자)을 평가로 뒀는데 그 문서 하나가 전체 창의 절반이라
#: 평가가 학습보다 커졌다. 문서 유형이 다른 둘(검증 보고서 · 제품 PRD)로 바꿨다.
EVAL_DOCS = {"00_PKM_필수데이터_샘플검증_보고서.md", "02_The_Urlist_PRD.md"}

#: 근거 한 덩어리의 크기. 운영 파이프라인이 청크 20건을 모아 한 번에 넘기므로
#: 학생에게도 비슷한 길이를 준다. 너무 짧으면 뽑을 업무가 없고, 너무 길면
#: 작은 모델의 컨텍스트를 넘긴다.
WINDOW_CHARS = 2400
STRIDE_CHARS = 1400  # 겹치게 밀어 표본 수를 늘린다

SYSTEM = (
    "근거 기반 프로젝트 업무 추출 에이전트다. 제공된 Chunk에 직접 근거가 있는 업무만 "
    "추출한다. 역할, 기술, 공수, 날짜를 추정하지 않는다. 근거가 없는 필드는 null 또는 "
    "빈 배열로 두고 missing_fields에 기록한다.\n"
    "모든 업무에 근거를 단다. 근거는 제공된 항목의 ref 값(E1, E2 …)으로만 적고, "
    "제공되지 않은 번호를 만들지 않는다."
)


def split_windows(text: str) -> list[str]:
    """제목 경계를 존중하면서 겹치는 창으로 자른다."""

    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    out: list[str] = []
    i = 0
    while i < len(text):
        window = text[i : i + WINDOW_CHARS]
        # 창 끝이 문장 중간이면 마지막 줄바꿈까지만 쓴다
        if i + WINDOW_CHARS < len(text):
            cut = window.rfind("\n")
            if cut > WINDOW_CHARS // 2:
                window = window[:cut]
        if len(window.strip()) >= 400:
            out.append(window.strip())
        i += STRIDE_CHARS
    return out


def to_evidence(window: str) -> list[dict]:
    """창을 운영과 같은 모양의 근거 목록으로 바꾼다(E1, E2 …)."""

    parts = [p.strip() for p in window.split("\n\n") if p.strip()]
    # 너무 잘게 쪼개지 않는다 — 운영은 청크 20건 안쪽이다
    merged: list[str] = []
    buf = ""
    for p in parts:
        if len(buf) + len(p) < 500:
            buf = f"{buf}\n\n{p}".strip()
        else:
            if buf:
                merged.append(buf)
            buf = p
    if buf:
        merged.append(buf)
    return [{"ref": f"E{n}", "text": t} for n, t in enumerate(merged[:20], start=1)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="창 개수 상한(0=전체)")
    ap.add_argument("--dry-run", action="store_true", help="교사 호출 없이 청크만 센다")
    ap.add_argument("--model", default="gpt-5.6-luna", help="교사 모델")
    ap.add_argument("--effort", default="low", help="교사 reasoning effort")
    args = ap.parse_args()

    docs = sorted(SOURCE_DIR.glob("*.md"))
    if not docs:
        print(f"원천 문서를 찾지 못했다: {SOURCE_DIR}", file=sys.stderr)
        return 1

    samples: list[tuple[str, str, list[dict]]] = []  # (문서명, split, evidence)
    for doc in docs:
        split = "eval" if doc.name in EVAL_DOCS else "train"
        for window in split_windows(doc.read_text(encoding="utf-8", errors="ignore")):
            ev = to_evidence(window)
            if len(ev) >= 2:
                samples.append((doc.name, split, ev))

    by_split: dict[str, int] = {}
    for _, s, _ in samples:
        by_split[s] = by_split.get(s, 0) + 1
    print(f"창 {len(samples)}개  " + "  ".join(f"{k}={v}" for k, v in sorted(by_split.items())))
    for doc in docs:
        n = sum(1 for d, _, _ in samples if d == doc.name)
        mark = " [평가 전용]" if doc.name in EVAL_DOCS else ""
        print(f"   {doc.name:46} {n:3}개{mark}")

    if args.dry_run:
        return 0

    if args.limit:
        random.Random(29).shuffle(samples)
        samples = samples[: args.limit]
        print(f"\n--limit 로 {len(samples)}개만 라벨링한다")

    from openai import OpenAI
    from services.task_extraction.service import ExtractionResult

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("OPENAI_API_KEY 가 없다.", file=sys.stderr)
        return 2
    client = OpenAI(api_key=api_key, timeout=180, max_retries=2)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = {s: (OUT_DIR / f"{s}.jsonl").open("w", encoding="utf-8") for s in ("train", "eval")}
    kept = {"train": 0, "eval": 0}
    failed = 0

    for i, (doc_name, split, ev) in enumerate(samples, start=1):
        user = f"기준 문서={doc_name}\n검색 근거={ev}"
        try:
            r = client.responses.parse(
                model=args.model,
                reasoning={"effort": args.effort},
                input=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                text_format=ExtractionResult,
            )
            parsed = r.output_parsed
        except Exception as exc:  # noqa: BLE001 - 한 건 실패로 전체를 멈추지 않는다
            failed += 1
            print(f"  [{i}/{len(samples)}] 실패 {type(exc).__name__}: {str(exc)[:90]}")
            continue

        if parsed is None or not parsed.tasks:
            # 업무가 안 나온 창은 버린다. 「빈 결과」만 잔뜩 배우면 학생이
            # 아무것도 안 뽑는 쪽으로 수렴한다.
            failed += 1
            continue

        files[split].write(
            json.dumps(
                {
                    "doc": doc_name,
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": user},
                        {"role": "assistant", "content": parsed.model_dump_json()},
                    ],
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        kept[split] += 1
        if i % 10 == 0:
            print(f"  [{i}/{len(samples)}] train={kept['train']} eval={kept['eval']} 실패={failed}")

    for f in files.values():
        f.close()
    print("")
    print(f"완료: train={kept['train']}  eval={kept['eval']}  버림={failed}")
    print(f"  {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
