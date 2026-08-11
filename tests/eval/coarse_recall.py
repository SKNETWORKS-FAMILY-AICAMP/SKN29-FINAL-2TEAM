"""coarse 단계의 문서 단위 Recall.

A안(요약 임베딩으로 문서를 먼저 좁히기)이 정답 문서를 후보에 남기는지 잰다.
이 숫자가 8/12 멘토링의 A vs A′ 판단 근거다 — 형식과 실행법은 README 참고.

`manage.py test` 가 안 돌리는 자리다. DB·RunPod 가 필요하고 질의마다 임베딩
값이 든다.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

import django

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from backend.db.document_pipeline import DocMetaRepository  # noqa: E402
from services.document_pipeline.runpod_client import embed_queries  # noqa: E402
from services.harness.registry import COARSE_TOP_N  # noqa: E402


def evaluate(golden: dict, *, top_n: int) -> dict:
    team_id = golden["team_id"]
    rows = []
    for case in golden["queries"]:
        relevant = set(case["relevant_doc_ids"])
        vector = embed_queries([case["query"]])[0]
        candidates = DocMetaRepository.coarse_search(
            team_id=team_id, query_vector=vector, top_n=top_n
        )
        found = {row["doc_id"] for row in candidates}
        hit = relevant & found
        rows.append(
            {
                "id": case["id"],
                "query": case["query"],
                # 질의별 recall. 정답이 여러 건이면 그중 몇 건을 남겼는가다.
                "recall": len(hit) / len(relevant) if relevant else 0.0,
                "missed": sorted(relevant - found),
                "candidates": [
                    (row["doc_id"], round(float(row["summary_score"]), 3)) for row in candidates
                ],
            }
        )

    # 질의 평균이다. 전체 정답 대비 비율이 아니라 — 정답이 많은 질의 하나가
    # 점수를 지배하면 "어떤 질의가 안 되는가"가 안 보인다.
    macro = sum(row["recall"] for row in rows) / len(rows) if rows else 0.0
    return {"top_n": top_n, "macro_recall": macro, "cases": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description="coarse 문서 Recall 측정")
    parser.add_argument("golden", help="골든셋 JSON 경로")
    parser.add_argument("--top-n", type=int, default=COARSE_TOP_N)
    args = parser.parse_args()

    golden = json.loads(pathlib.Path(args.golden).read_text(encoding="utf-8"))
    report = evaluate(golden, top_n=args.top_n)

    print(f"coarse Recall@{report['top_n']} (문서 단위) = {report['macro_recall']:.3f}")
    for case in report["cases"]:
        mark = "OK " if case["recall"] == 1.0 else "MISS"
        print(f"  [{mark}] {case['id']} recall={case['recall']:.2f}  {case['query'][:50]}")
        if case["missed"]:
            print(f"         놓친 문서: {', '.join(case['missed'])}")
            print(f"         뽑힌 후보: {case['candidates']}")
    # 놓친 것이 있으면 0 이 아닌 값으로 끝낸다 — CI 에 걸 때 쓴다.
    return 0 if report["macro_recall"] == 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
