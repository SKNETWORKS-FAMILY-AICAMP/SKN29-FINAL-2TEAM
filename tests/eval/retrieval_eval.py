"""검색 품질(파싱·청킹·임베딩) 측정. 에이전트를 거치지 않는다.

**왜 에이전트를 안 거치나** — 재려는 것이 파싱·청킹·임베딩이기 때문이다. 대화로
재면 LLM 의 회차별 흔들림과 도구 선택이 섞여 들어와, 숫자가 나빠졌을 때 청킹이
나빠진 건지 모델이 그날 이상했던 건지 가를 수 없다. 여기서는 질의를 임베딩해
`vec_idx` 를 직접 때린다 — 싸고, 반복해도 같은 답이 나오고, 원인이 한 곳이다.

실행 (컨테이너 안):

    docker compose -f infra/docker/docker-compose.yml exec -T web \
      python tests/eval/retrieval_eval.py

    --top-k N     상위 몇 건까지 볼지 (기본 10)
    --json PATH   결과를 파일로 남긴다. 고도화 전후 비교는 이 파일끼리 한다.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app" if Path("/app/manage.py").exists() else str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from backend.db.connection import database_connection  # noqa: E402
from services.document_pipeline.runpod_client import embed_queries  # noqa: E402


#: 한 번에 임베딩할 질의 수. **37건을 한 번에 넘기면 워커가 FAILED 로 떨어진다**
#: (2026-08-28 실측, 16건은 정상). 제품은 `document_search` 가 질의 하나씩만
#: 부르므로 이 한도에 닿은 적이 없다 — 평가만 여러 건을 모아 부른다.
EMBED_BATCH = 16


def embed_all(texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        out.extend(embed_queries(texts[i : i + EMBED_BATCH]))
    return out


GOLDEN = Path(__file__).resolve().parent / "golden" / "retrieval.json"

#: 상위 몇 건까지를 「잠식」으로 볼지. 다른 프로젝트 문서가 여기 들어오면 샌 것이다.
CONTAMINATION_K = 3

SEARCH = """
    SELECT c.chunk_id, d.file_name, c.search_text, b.heading_path,
           1 - (v.embedding <=> %s::vector) AS score
      FROM vec_idx v
      JOIN chunk c     ON c.chunk_id = v.chunk_id AND c.is_active
      JOIN doc_block b ON b.block_id = c.block_id
      JOIN doc d       ON d.doc_id = b.doc_id AND b.revision = d.cur_revision
     WHERE v.is_active
       AND d.deleted = false AND d.access_revoked = false
       AND d.team_id = %s
     ORDER BY v.embedding <=> %s::vector
     LIMIT %s
"""


def flat(text: str) -> str:
    """공백을 전부 지운다.

    PDF 파서는 같은 문장을 줄바꿈·공백을 달리해 내놓는다. 앵커를 원문 그대로
    적어 두고 여기서 납작하게 눌러 비교해야, 청킹 방식을 바꿔도 같은 정답지가
    계속 쓰인다.
    """
    return re.sub(r"\s+", "", text or "")


def team_id(cursor) -> str:
    cursor.execute("SELECT team_id FROM team ORDER BY team_id LIMIT 1")
    row = cursor.fetchone()
    if row is None:
        raise SystemExit("팀이 없다. 문서를 먼저 수집할 것.")
    return row["team_id"]


def preflight(cursor, queries, tid):
    """앵커가 **지금 색인 안에 실제로 있는지** 먼저 본다.

    없으면 검색이 못 찾은 것이 아니라 **청킹이 앵커를 두 청크로 잘라 놓은
    것**이다. 이 둘을 안 가르면 청킹을 바꿀 때마다 검색이 나빠진 것처럼 보인다.
    """
    cursor.execute(
        """
        SELECT d.file_name, c.search_text
          FROM chunk c
          JOIN doc_block b ON b.block_id = c.block_id
          JOIN doc d       ON d.doc_id = b.doc_id AND b.revision = d.cur_revision
         WHERE c.is_active AND d.deleted = false AND d.team_id = %s
        """,
        (tid,),
    )
    by_doc: dict[str, list[str]] = {}
    for row in cursor.fetchall():
        by_doc.setdefault(row["file_name"], []).append(flat(row["search_text"]))

    missing, ambiguous = [], []
    for q in queries:
        want, anchor = q["expect"]["document"], flat(q["expect"]["anchor"])
        hosts = [name for name, texts in by_doc.items() if any(anchor in t for t in texts)]
        if want not in hosts:
            missing.append((q["id"], q["expect"]["document"], q["expect"]["anchor"]))
        elif len(hosts) > 1:
            ambiguous.append((q["id"], hosts))
    return by_doc, missing, ambiguous


def project_index(golden: dict) -> dict[str, str]:
    """문서 → 소속. 정답지의 `projects` 와 문서 명세가 정본이다.

    파일 이름 규칙(접두사)으로 가르지 않는다. 처음에 그렇게 했다가, 정답 문서를
    부분 문자열(「과업지시서」)로 적은 것이 두 프로젝트의 파일에 **다 걸려**
    잠식률이 거꾸로 나왔다 — 자기 프로젝트 문서를 남의 것으로 셌다.

    `documents/specs/` 는 파일 하나가 프로젝트 하나다(`noise_*` 만 예외로 묶는다).
    거기서 `target` 을 읽어 소속을 채운다 — 정답지에 목록을 두 번 적지 않는다.
    """
    index = {
        name: project
        for project, names in golden.get("projects", {}).items()
        for name in names
    }

    specs = Path(__file__).resolve().parent / "documents" / "specs"
    for path in sorted(specs.glob("*.py")):
        if path.name.startswith("_"):
            continue
        owner = "노이즈" if path.stem.startswith("noise") else path.stem
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:  # noqa: BLE001 — 명세 하나가 깨져도 나머지는 잰다
            print(f"⚠ 명세를 읽지 못했다: {path.name} ({exc})")
            continue
        for doc in getattr(module, "DOCUMENTS", []):
            index[doc["target"]] = owner
    return index


def load_golden() -> dict:
    """`retrieval.json` 에 `queries_*.json` 을 합친다.

    프로젝트별 정답지를 나눠 만들기 때문이다 — 한 파일에 모아 두면 여럿이
    동시에 쓸 때 서로를 덮어쓴다.
    """
    base = json.loads(GOLDEN.read_text(encoding="utf-8"))
    seen = {q["id"] for q in base["queries"]}
    for path in sorted(GOLDEN.parent.glob("queries_*.json")):
        extra = json.loads(path.read_text(encoding="utf-8"))
        for q in extra.get("queries", []):
            if q["id"] in seen:
                raise SystemExit(f"질의 id 가 겹친다: {q['id']} ({path.name})")
            seen.add(q["id"])
            base["queries"].append(q)
    return base


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    golden = load_golden()
    queries = golden["queries"]
    projects = project_index(golden)

    with database_connection() as connection:
        with connection.cursor() as cursor:
            tid = team_id(cursor)
            by_doc, missing, ambiguous = preflight(cursor, queries, tid)

            print(f"팀 {tid} · 문서 {len(by_doc)}종 · 청크 {sum(len(v) for v in by_doc.values())}개")
            print(f"질의 {len(queries)}개 · top_k={args.top_k}\n")

            unknown = sorted({q["expect"]["document"] for q in queries} - set(by_doc))
            if unknown:
                raise SystemExit(
                    "정답지가 가리키는 문서가 색인에 없다 — 이름이 바뀌었거나 수집이 덜 됐다: "
                    + str(unknown)
                )

            if missing:
                print(f"⚠ 앵커를 색인에서 못 찾음 {len(missing)}건 — 청킹이 문장을 잘랐거나 파싱이 흘렸다:")
                for qid, doc, anchor in missing:
                    print(f"    {qid}  {doc}  「{anchor}」")
                print()
            if ambiguous:
                print(f"⚠ 앵커가 여러 문서에 있음 {len(ambiguous)}건 — 변별력이 없으니 앵커를 바꿀 것:")
                for qid, hosts in ambiguous:
                    print(f"    {qid}  {hosts}")
                print()

            vectors = embed_all([q["query"] for q in queries])

            results, hits_at = [], {1: 0, 5: 0, 10: 0}
            rr_sum, contaminated, noise_hit = 0.0, 0, 0
            for q, vector in zip(queries, vectors):
                want, anchor = q["expect"]["document"], flat(q["expect"]["anchor"])
                cursor.execute(SEARCH, (str(vector), tid, str(vector), args.top_k))
                rows = cursor.fetchall()

                rank = None
                for i, row in enumerate(rows, start=1):
                    if row["file_name"] == want and anchor in flat(row["search_text"]):
                        rank = i
                        break

                want_project = projects.get(want)
                others = [
                    (r["file_name"], projects.get(r["file_name"], want_project))
                    for r in rows[:CONTAMINATION_K]
                ]
                leaked = [n for n, owner in others if owner not in (want_project, "노이즈")]
                noised = [n for n, owner in others if owner == "노이즈"]
                if leaked:
                    contaminated += 1
                if noised:
                    noise_hit += 1

                if rank:
                    rr_sum += 1 / rank
                    for k in hits_at:
                        if rank <= k:
                            hits_at[k] += 1

                results.append(
                    {
                        "id": q["id"],
                        "query": q["query"],
                        "rank": rank,
                        "top1_document": rows[0]["file_name"] if rows else None,
                        "top1_score": round(float(rows[0]["score"]), 4) if rows else None,
                        "leaked": leaked,
                        "noise": noised,
                    }
                )

    n = len(queries)
    print(f"{'질의':6} {'순위':>4}  {'상위1 점수':>9}  상위1 문서")
    for r in results:
        rank = str(r["rank"]) if r["rank"] else "—"
        print(f"  {r['id']:5} {rank:>4}  {str(r['top1_score']):>9}  {(r['top1_document'] or '')[:44]}")

    print()
    print(f"  Recall@1   {hits_at[1]/n:6.1%}   ({hits_at[1]}/{n})")
    print(f"  Recall@5   {hits_at[5]/n:6.1%}   ({hits_at[5]}/{n})")
    print(f"  Recall@10  {hits_at[10]/n:6.1%}   ({hits_at[10]}/{n})")
    print(f"  MRR        {rr_sum/n:6.3f}")
    print(f"  잠식률     {contaminated/n:6.1%}   (상위 {CONTAMINATION_K} 에 다른 프로젝트 문서)")
    print(f"  노이즈혼입 {noise_hit/n:6.1%}   (상위 {CONTAMINATION_K} 에 배경 문서)")
    print(f"  앵커 정착  {(n-len(missing))/n:6.1%}   ({n-len(missing)}/{n})")

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "top_k": args.top_k,
                    "queries": n,
                    "recall": {str(k): v / n for k, v in hits_at.items()},
                    "mrr": rr_sum / n,
                    "contamination": contaminated / n,
                    "noise_hit": noise_hit / n,
                    "anchor_present": (n - len(missing)) / n,
                    "missing_anchors": [m[0] for m in missing],
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\n→ {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
