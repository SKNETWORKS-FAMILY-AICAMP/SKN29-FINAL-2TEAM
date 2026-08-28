"""원빈님 인계 검색 정답지로 벡터 단독과 하이브리드 검색을 비교한다.

평가 문서 HTML을 제목 절 단위로 읽고 운영과 같은 EmbeddingGemma 질의/문서
벡터를 만든다. lexical 점수는 로컬 PostgreSQL의 ``simple`` FTS와 ``pg_trgm``
함수를 직접 호출하므로 운영 SQL과 같은 연산자를 검증한다.

    docker compose -f infra/docker/docker-compose.yml exec -T web \
      python scripts/evaluate_document_search.py

임베딩은 ``.codex_staging/document-search-eval-embeddings.json``에 캐시한다.
``--refresh-embeddings``를 주면 다시 만든다. 결과 보고서는 JSON으로 표준 출력한다.
"""

from __future__ import annotations

import argparse
import html
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from backend.db.connection import database_connection  # noqa: E402
from backend.db.document_pipeline import (  # noqa: E402
    HYBRID_EXACT_WEIGHT,
    HYBRID_FTS_WEIGHT,
    HYBRID_TRIGRAM_WEIGHT,
    lexical_tsquery,
)
from services.document_pipeline.errors import RunPodRequestError  # noqa: E402
from services.document_pipeline.runpod_client import embed_queries  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT_DIR = ROOT / "tests" / "eval" / "documents"
GOLD_PATH = ROOT / "tests" / "eval" / "golden" / "document_search_hybrid_legacy.json"
CACHE_PATH = ROOT / ".codex_staging" / "document-search-eval-embeddings.json"

TOP_K = 20
CANDIDATE_K = TOP_K * 3
LEXICAL_CRITICAL_IDS = {"Q03", "Q04", "Q05", "Q06", "Q08", "Q12", "Q13", "Q14"}

DOCUMENT_ALIASES = {
    "01_과업지시서.html": "과업지시서",
    "02_요구사항정의서.html": "요구사항정의서",
    "03_인력운영계획서.html": "인력운영계획서",
    "04_WBS_마일스톤.html": "WBS",
    "05_기술검토회의록.html": "기술검토회의록",
    "06_타사업_그룹웨어_유지보수.html": "그룹웨어 과업지시서",
    "07_그룹웨어_SLA합의서.html": "그룹웨어 SLA",
    "08_그룹웨어_개선요청_접수내역.html": "그룹웨어 개선요청",
}


class SectionParser(HTMLParser):
    """h2/h3 절과 그 아래의 사람이 읽는 텍스트를 보존한다."""

    def __init__(self) -> None:
        super().__init__()
        self.heading_tag: str | None = None
        self.heading_parts: list[str] = []
        self.path: list[str] = []
        self.body_parts: list[str] = []
        self.sections: list[tuple[list[str], str]] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"style", "script"}:
            self.skip_depth += 1
        if tag in {"h2", "h3"}:
            self._flush()
            self.heading_tag = tag
            self.heading_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"style", "script"} and self.skip_depth:
            self.skip_depth -= 1
        if tag == self.heading_tag:
            heading = _clean(" ".join(self.heading_parts))
            if tag == "h2":
                self.path = [heading]
            else:
                self.path = self.path[:1] + [heading]
            self.heading_tag = None
            self.heading_parts = []

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if self.heading_tag:
            self.heading_parts.append(data)
        elif self.path:
            self.body_parts.append(data)

    def close(self) -> None:
        super().close()
        self._flush()

    def _flush(self) -> None:
        body = _clean(" ".join(self.body_parts))
        if self.path and body:
            self.sections.append((list(self.path), body))
        self.body_parts = []


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def load_corpus() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for file_name, alias in DOCUMENT_ALIASES.items():
        parser = SectionParser()
        parser.feed((DOCUMENT_DIR / file_name).read_text(encoding="utf-8"))
        parser.close()
        for index, (heading_path, body) in enumerate(parser.sections):
            rows.append(
                {
                    "id": f"{file_name}:{index}",
                    "document": alias,
                    "heading_path": heading_path,
                    "section": _section_number(heading_path[-1]),
                    "search_text": " > ".join(heading_path) + "\n" + body,
                    "text": body,
                }
            )
    return rows


def _section_number(heading: str) -> str:
    match = re.match(r"\s*(\d+(?:\.\d+)?)", heading)
    return match.group(1) if match else heading


def _vectors(texts: list[str], *, refresh: bool) -> list[list[float]]:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cache: dict[str, list[float]] = {}
    if CACHE_PATH.exists() and not refresh:
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    missing = [text for text in texts if text not in cache]
    for start in range(0, len(missing), 8):
        batch = missing[start : start + 8]
        for text, vector in zip(batch, _embed_with_split(batch), strict=True):
            cache[text] = vector
    if missing:
        CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return [cache[text] for text in texts]


def _embed_with_split(texts: list[str]) -> list[list[float]]:
    """RunPod 배치 한도가 낮은 워커에서도 같은 입력을 안정적으로 처리한다."""

    try:
        return embed_queries(texts)
    except RunPodRequestError:
        if len(texts) == 1:
            raise
        middle = len(texts) // 2
        return _embed_with_split(texts[:middle]) + _embed_with_split(texts[middle:])


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    lnorm = math.sqrt(sum(a * a for a in left))
    rnorm = math.sqrt(sum(b * b for b in right))
    return max(0.0, dot / (lnorm * rnorm)) if lnorm and rnorm else 0.0


def lexical_scores(query: str, texts: list[str]) -> list[tuple[float, float, float]]:
    """운영과 같은 PostgreSQL FTS/trigram/정확 포함 원점수를 받는다."""

    with database_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT ts_rank_cd(to_tsvector('simple', item.text),
                              to_tsquery('simple', %s)) AS fts,
                   word_similarity(%s, item.text) AS trigram,
                   CASE WHEN position(lower(%s) IN lower(item.text)) > 0
                        THEN 1.0 ELSE 0.0 END AS exact
              FROM unnest(%s::text[]) WITH ORDINALITY AS item(text, ordinal)
             ORDER BY item.ordinal
            """,
            (lexical_tsquery(query), query, query, texts),
        )
        return [(float(row["fts"]), float(row["trigram"]), float(row["exact"])) for row in cursor]


def _normalize(values: list[float]) -> list[float]:
    maximum = max(values, default=0.0)
    return [value / maximum if maximum else 0.0 for value in values]


def rank(
    corpus: list[dict[str, Any]],
    query_vector: list[float],
    corpus_vectors: list[list[float]],
    lexical: list[tuple[float, float, float]],
    *,
    vector_weight: float,
    fts_weight: float,
    trigram_weight: float,
    exact_weight: float,
) -> list[dict[str, Any]]:
    vector_raw = [_cosine(query_vector, vector) for vector in corpus_vectors]
    fts_raw = [row[0] for row in lexical]
    trigram_raw = [row[1] for row in lexical]
    exact_raw = [row[2] for row in lexical]

    candidates = set(sorted(range(len(corpus)), key=vector_raw.__getitem__, reverse=True)[:CANDIDATE_K])
    candidates.update(sorted(range(len(corpus)), key=fts_raw.__getitem__, reverse=True)[:CANDIDATE_K])
    candidates.update(sorted(range(len(corpus)), key=trigram_raw.__getitem__, reverse=True)[:CANDIDATE_K])

    vector_score = _normalize([vector_raw[i] if i in candidates else 0.0 for i in range(len(corpus))])
    fts_score = _normalize([fts_raw[i] if i in candidates else 0.0 for i in range(len(corpus))])
    trigram_score = _normalize([trigram_raw[i] if i in candidates else 0.0 for i in range(len(corpus))])
    scored: list[dict[str, Any]] = []
    for index in candidates:
        lexical_score = (
            fts_weight * fts_score[index]
            + trigram_weight * trigram_score[index]
            + exact_weight * exact_raw[index]
        )
        retrieval_score = vector_weight * vector_score[index] + (1 - vector_weight) * lexical_score
        scored.append(
            corpus[index]
            | {
                "vector_score": vector_score[index],
                "fts_score": fts_score[index],
                "trigram_score": trigram_score[index],
                "exact_score": exact_raw[index],
                "lexical_score": lexical_score,
                "retrieval_score": retrieval_score,
            }
        )
    rows = sorted(scored, key=lambda row: (-row["retrieval_score"], row["id"]))[:TOP_K]
    return [row | {"rank": index} for index, row in enumerate(rows, start=1)]


def _expected_match(row: dict[str, Any], expected: dict[str, str]) -> bool:
    if row["document"] != expected["document"]:
        return False
    section = row["section"]
    spec = expected["section"]
    range_match = re.match(r"(\d+(?:\.\d+)?)\s*~\s*(\d+(?:\.\d+)?)", spec)
    if range_match:
        start, end = (tuple(map(int, item.split("."))) for item in range_match.groups())
        current = tuple(map(int, section.split("."))) if re.fullmatch(r"\d+(?:\.\d+)?", section) else ()
        return bool(current) and start <= current <= end
    choices = re.findall(r"\d+(?:\.\d+)?", spec.split("(", 1)[0])
    return any(section == choice or section.startswith(choice + ".") for choice in choices)


def _must_not_match(row: dict[str, Any], spec: str) -> bool:
    aliases = sorted(DOCUMENT_ALIASES.values(), key=len, reverse=True)
    alias = next((name for name in aliases if spec.startswith(name)), None)
    if alias is None or row["document"] != alias:
        return False
    section = spec[len(alias) :].strip()
    return not section or row["section"] == section or row["section"].startswith(section + ".")


def score(queries: list[dict[str, Any]], rankings: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    relevant_total = 0
    relevant_found = 0
    reciprocal_ranks: list[float] = []
    precisions = {cutoff: [] for cutoff in (5, 8, TOP_K)}
    query_hits = 0
    contamination = 0
    lexical_success = 0
    details = []
    for query in queries:
        rows = rankings[query["id"]]
        expected_hits = [any(_expected_match(row, expected) for row in rows) for expected in query["expected"]]
        relevant_total += len(expected_hits)
        relevant_found += sum(expected_hits)
        relevant_positions = [
            index + 1
            for index, row in enumerate(rows)
            if any(_expected_match(row, expected) for expected in query["expected"])
        ]
        first_rank = min(relevant_positions, default=None)
        query_hits += int(first_rank is not None)
        reciprocal_ranks.append(1 / first_rank if first_rank else 0.0)
        for cutoff in precisions:
            precisions[cutoff].append(sum(position <= cutoff for position in relevant_positions) / cutoff)
        contaminated = any(
            _must_not_match(row, forbidden)
            for row in rows[:3]
            for forbidden in query.get("must_not_cite", [])
        )
        contamination += int(contaminated)
        if query["id"] in LEXICAL_CRITICAL_IDS:
            lexical_success += int(first_rank is not None)
        details.append(
            {
                "id": query["id"],
                "first_relevant_rank": first_rank,
                "expected_found": sum(expected_hits),
                "expected_total": len(expected_hits),
                "contaminated_top3": contaminated,
            }
        )
    lexical_count = sum(query["id"] in LEXICAL_CRITICAL_IDS for query in queries)
    return {
        "query_recall_at_20": query_hits / len(queries),
        "evidence_recall_at_20": relevant_found / relevant_total,
        "precision_at_5": sum(precisions[5]) / len(precisions[5]),
        "precision_at_8": sum(precisions[8]) / len(precisions[8]),
        "precision_at_20": sum(precisions[TOP_K]) / len(precisions[TOP_K]),
        "mrr": sum(reciprocal_ranks) / len(reciprocal_ranks),
        "contamination_at_3": contamination / len(queries),
        "lexical_critical_success": lexical_success / lexical_count if lexical_count else None,
        "details": details,
    }


def compare_rankings(
    queries: list[dict[str, Any]],
    baseline: dict[str, list[dict[str, Any]]],
    candidate: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    comparisons = []
    for query in queries:
        query_id = query["id"]

        def first_relevant(rows: list[dict[str, Any]]) -> tuple[int | None, dict[str, Any] | None]:
            match = next(
                (
                    (index, row)
                    for index, row in enumerate(rows, start=1)
                    if any(_expected_match(row, expected) for expected in query["expected"])
                ),
                None,
            )
            return match if match else (None, None)

        vector_rank, vector_relevant = first_relevant(baseline[query_id])
        hybrid_rank, hybrid_relevant = first_relevant(candidate[query_id])
        delta = None if vector_rank is None or hybrid_rank is None else vector_rank - hybrid_rank
        comparisons.append(
            {
                "id": query_id,
                "query": query["query"],
                "vector_rank": vector_rank,
                "hybrid_rank": hybrid_rank,
                "rank_improvement": delta,
                "hybrid_first_relevant": _score_diagnostic(hybrid_relevant),
                "hybrid_top_result": _score_diagnostic(candidate[query_id][0]),
                "status": (
                    "recovered" if vector_rank is None and hybrid_rank is not None
                    else "lost" if vector_rank is not None and hybrid_rank is None
                    else "improved" if delta is not None and delta > 0
                    else "regressed" if delta is not None and delta < 0
                    else "unchanged"
                ),
            }
        )
    return {
        "queries": comparisons,
        "regressions": [row for row in comparisons if row["status"] in {"lost", "regressed"}],
        "improvements": [row for row in comparisons if row["status"] in {"recovered", "improved"}],
    }


def _score_diagnostic(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "document": row["document"],
        "section": row["section"],
        "vector_score": row["vector_score"],
        "fts_score": row["fts_score"],
        "trigram_score": row["trigram_score"],
        "exact_score": row["exact_score"],
        "lexical_score": row["lexical_score"],
        "retrieval_score": row["retrieval_score"],
    }


def score_by_tag(
    queries: list[dict[str, Any]], rankings: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    tags = sorted({tag for query in queries for tag in query.get("tags", [])})
    return {
        tag: {
            "query_count": len(tagged),
            **score(tagged, rankings),
        }
        for tag in tags
        if (tagged := [query for query in queries if tag in query.get("tags", [])])
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-embeddings", action="store_true")
    parser.add_argument("--output", type=Path, help="전체 평가·질의별 진단 JSON 저장 경로")
    args = parser.parse_args()

    corpus = load_corpus()
    golden = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    queries = golden["queries"]
    query_ids = {query["id"] for query in queries}
    dev_query_ids = set(golden["splits"]["development"])
    holdout_query_ids = set(golden["splits"]["holdout"])
    if dev_query_ids & holdout_query_ids:
        raise ValueError("development와 holdout 질의 ID가 겹칩니다.")
    if dev_query_ids | holdout_query_ids != query_ids:
        raise ValueError("모든 평가 질의는 development 또는 holdout에 정확히 한 번 속해야 합니다.")
    texts = [row["search_text"] for row in corpus]
    all_vectors = _vectors(texts + [query["query"] for query in queries], refresh=args.refresh_embeddings)
    corpus_vectors = all_vectors[: len(corpus)]
    query_vectors = all_vectors[len(corpus) :]
    lexical_by_query = {query["id"]: lexical_scores(query["query"], texts) for query in queries}

    variants = {
        "vector": (1.0, HYBRID_FTS_WEIGHT, HYBRID_TRIGRAM_WEIGHT, HYBRID_EXACT_WEIGHT),
        "hybrid_40": (0.4, HYBRID_FTS_WEIGHT, HYBRID_TRIGRAM_WEIGHT, HYBRID_EXACT_WEIGHT),
        "hybrid_50": (0.5, HYBRID_FTS_WEIGHT, HYBRID_TRIGRAM_WEIGHT, HYBRID_EXACT_WEIGHT),
        "hybrid_60": (0.6, HYBRID_FTS_WEIGHT, HYBRID_TRIGRAM_WEIGHT, HYBRID_EXACT_WEIGHT),
        "hybrid_70": (0.7, HYBRID_FTS_WEIGHT, HYBRID_TRIGRAM_WEIGHT, HYBRID_EXACT_WEIGHT),
    }
    rankings: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for name, weights in variants.items():
        rankings[name] = {
            query["id"]: rank(
                corpus, query_vector, corpus_vectors, lexical_by_query[query["id"]],
                vector_weight=weights[0], fts_weight=weights[1],
                trigram_weight=weights[2], exact_weight=weights[3],
            )
            for query, query_vector in zip(queries, query_vectors, strict=True)
        }

    report: dict[str, Any] = {
        "corpus_sections": len(corpus),
        "query_count": len(queries),
        "thresholds": {
            "query_recall_at_20": 0.90,
            "precision_not_below_vector": True,
            "mrr_not_below_vector": True,
            "lexical_critical_success": 1.0,
            "contamination_at_3": 0.0,
        },
        "variants": {},
    }
    for name, by_query in rankings.items():
        report["variants"][name] = {
            "all": score(queries, by_query),
            "dev": score([q for q in queries if q["id"] in dev_query_ids], by_query),
            "holdout": score([q for q in queries if q["id"] in holdout_query_ids], by_query),
            "by_tag": score_by_tag(queries, by_query),
        }
    vector = report["variants"]["vector"]["all"]
    candidates = [name for name in variants if name.startswith("hybrid_")]
    dev_queries = [query for query in queries if query["id"] in dev_query_ids]
    regression_free = [
        name for name in candidates
        if not compare_rankings(
            dev_queries, rankings["vector"], rankings[name],
        )["regressions"]
    ]
    selection_pool = regression_free or candidates
    selected = max(
        selection_pool,
        key=lambda name: (
            report["variants"][name]["dev"]["evidence_recall_at_20"],
            report["variants"][name]["dev"]["mrr"],
            report["variants"][name]["dev"]["precision_at_20"],
        ),
    )
    report["selected_variant"] = selected
    report["selection_policy"] = {
        "selection_data": "development_only",
        "holdout_used_for_selection": False,
        "development_regression_guard": True,
        "regression_free_candidates": regression_free,
        "fallback_used": not regression_free,
        "ranking": ["evidence_recall_at_20", "mrr", "precision_at_20"],
    }
    report["selected_comparison"] = compare_rankings(
        queries, rankings["vector"], rankings[selected],
    )
    hybrid = report["variants"][selected]["all"]
    report["selected_variant_passed"] = (
        hybrid["query_recall_at_20"] >= 0.90
        and hybrid["precision_at_20"] >= vector["precision_at_20"]
        and hybrid["mrr"] >= vector["mrr"]
        and hybrid["lexical_critical_success"] == 1.0
        and hybrid["contamination_at_3"] == 0.0
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["selected_variant_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
