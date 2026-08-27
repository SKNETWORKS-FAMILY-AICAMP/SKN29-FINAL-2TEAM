"""동결 전 Core DEV cohort를 동일 규칙으로 자동 집계한다."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / "outputs" / "eval-v2-results"
DEFAULT_CANDIDATE = "AG004/AV035"

# S08은 실행 미승인, S10/S11은 Expansion이므로 이 Core DEV cohort에 포함하지 않는다.
CORE_DEV_COHORT = {
    "S01-DEV-001": {"fixture_version": 1, "planned": 3},
    "S02-DEV-001": {"fixture_version": 1, "planned": 3},
    "S03-DEV-001": {"fixture_version": 1, "planned": 3},
    "S04-DEV-001": {"fixture_version": 2, "planned": 9},
    "S05A-DEV-001": {"fixture_version": 1, "planned": 3},
    "S05B-DEV-001": {"fixture_version": 1, "planned": 3},
    "S06-DEV-001": {"fixture_version": 1, "planned": 3},
    "S07-DEV-001": {"fixture_version": 1, "planned": 3},
    "S09A-DEV-001": {"fixture_version": 1, "planned": 3},
    "S09B-DEV-001": {"fixture_version": 1, "planned": 3},
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--candidate-id", default=DEFAULT_CANDIDATE)
    return parser


def build_portfolio(results_root: Path, candidate_id: str) -> dict:
    by_fixture: dict[str, list[dict]] = {key: [] for key in CORE_DEV_COHORT}
    invalid: list[dict] = []

    for run_dir in sorted(results_root.glob("v2-*")):
        manifest_path = run_dir / "v2_run_manifest.json"
        results_path = run_dir / "v2_scenario_results.jsonl"
        if not manifest_path.is_file() or not results_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("candidate_id") != candidate_id:
            continue
        results = [
            json.loads(line)
            for line in results_path.read_text(encoding="utf-8").splitlines()
            if line
        ]
        matching = [
            result
            for result in results
            if result.get("fixture_id") in CORE_DEV_COHORT
            and result.get("fixture_version")
            == CORE_DEV_COHORT[result["fixture_id"]]["fixture_version"]
        ]
        if not matching:
            continue
        disposition_path = run_dir / "v2_disposition.json"
        if disposition_path.is_file():
            disposition = json.loads(disposition_path.read_text(encoding="utf-8"))
            if disposition.get("status") == "INVALID_EVALUATION_INFRA":
                invalid.append({
                    "eval_run_id": manifest["eval_run_id"],
                    "reason": disposition["reason"],
                })
                continue
        for result in matching:
            by_fixture[result["fixture_id"]].append({
                "eval_run_id": manifest["eval_run_id"],
                "scenario_result": result["scenario_result"],
                "attack_profile": manifest.get("attack_profile"),
                "criteria": result.get("criteria") or [],
            })

    variants: dict[str, dict] = {}
    total_counts: Counter = Counter()
    pass_rates: list[float] = []
    complete = True
    for fixture_id, specification in CORE_DEV_COHORT.items():
        runs = by_fixture[fixture_id]
        counts = Counter(run["scenario_result"] for run in runs)
        planned = specification["planned"]
        if len(runs) != planned:
            complete = False
        pass_rate = counts["PASS"] / planned if planned else 0.0
        pass_rates.append(pass_rate)
        total_counts.update(counts)
        variants[fixture_id] = {
            "fixture_version": specification["fixture_version"],
            "planned": planned,
            "observed": len(runs),
            "counts": dict(sorted(counts.items())),
            "strict_pass_rate": round(pass_rate, 4),
            "attack_profiles": dict(sorted(Counter(
                run["attack_profile"] for run in runs if run["attack_profile"]
            ).items())),
        }

    planned_total = sum(item["planned"] for item in CORE_DEV_COHORT.values())
    observed_total = sum(len(runs) for runs in by_fixture.values())
    return {
        "protocol": "AGENT_EVAL_V2",
        "cohort": "CORE_DEV_PRE_FREEZE",
        "candidate_id": candidate_id,
        "complete": complete,
        "variant_count": len(CORE_DEV_COHORT),
        "planned_run_count": planned_total,
        "observed_run_count": observed_total,
        "counts": dict(sorted(total_counts.items())),
        "run_weighted_strict_pass_rate": round(
            total_counts["PASS"] / planned_total if planned_total else 0.0, 4
        ),
        "variant_macro_strict_pass_rate": round(
            sum(pass_rates) / len(pass_rates) if pass_rates else 0.0, 4
        ),
        "invalid_evaluation_infra_attempt_count": len(invalid),
        "invalid_evaluation_infra_attempts": invalid,
        "variants": variants,
        "excluded": {
            "S08": "NOT_AUTHORIZED",
            "S10_S11": "EXPANSION_TEAM_MEMBER_TRACK",
            "LEGACY": "SEPARATE_PROTOCOL",
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    payload = build_portfolio(args.results_root, args.candidate_id)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
