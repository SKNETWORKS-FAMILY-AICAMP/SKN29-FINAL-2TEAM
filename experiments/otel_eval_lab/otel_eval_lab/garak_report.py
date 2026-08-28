from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .models import MetricScore


def summarize_garak_report(path: Path) -> tuple[dict[str, Any], list[MetricScore]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    types = Counter(str(row.get("entry_type") or "unknown") for row in rows)
    scores: list[MetricScore] = []

    for row in rows:
        if row.get("entry_type") != "eval":
            continue
        passed = int(row.get("passed") or 0)
        total = int(row.get("total_evaluated") or 0)
        if total <= 0:
            continue
        pass_rate = passed / total
        probe = str(row.get("probe") or row.get("probe_classname") or "unknown_probe")
        detector = str(row.get("detector") or "unknown_detector")
        scores.append(
            MetricScore(
                evaluator="garak",
                metric=f"{probe}:{detector}",
                score=pass_rate,
                passed=passed == total,
                reason=f"{passed}/{total} responses passed; attack success rate={1-pass_rate:.3f}",
            )
        )

    return {"rows": len(rows), "entry_types": dict(types), "eval_scores": len(scores)}, scores
