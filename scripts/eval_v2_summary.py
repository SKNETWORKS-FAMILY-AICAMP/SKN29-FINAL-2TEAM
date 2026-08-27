"""분리 저장된 Agent Eval V2 run을 disposition을 반영해 자동 집계한다."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / "outputs" / "eval-v2-results"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--fixture-id")
    parser.add_argument("--fixture-version", type=int)
    parser.add_argument("--attack-profile")
    parser.add_argument("--candidate-id")
    parser.add_argument(
        "--planned",
        type=int,
        help="동결된 round의 계획 slot 수. 생략하면 포함된 유효 DEV 실행 수를 사용한다.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    from services.evaluation.v2_scoring import aggregate_scenario_results

    args = _parser().parse_args(argv)
    included: list[dict] = []
    invalid: list[dict] = []
    criterion_counts: dict[str, Counter] = {}
    for run_dir in sorted(args.results_root.glob("v2-*")):
        manifest_path = run_dir / "v2_run_manifest.json"
        results_path = run_dir / "v2_scenario_results.jsonl"
        if not manifest_path.is_file() or not results_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if args.candidate_id and manifest.get("candidate_id") != args.candidate_id:
            continue
        if args.fixture_id and args.fixture_id not in manifest.get("planned_scenarios", []):
            continue
        if args.attack_profile and manifest.get("attack_profile") != args.attack_profile:
            continue
        results = [
            json.loads(line)
            for line in results_path.read_text(encoding="utf-8").splitlines()
            if line
        ]
        matching_results = [
            result
            for result in results
            if (not args.fixture_id or result.get("fixture_id") == args.fixture_id)
            and (
                args.fixture_version is None
                or result.get("fixture_version") == args.fixture_version
            )
        ]
        if not matching_results:
            continue
        disposition_path = run_dir / "v2_disposition.json"
        if disposition_path.is_file():
            disposition = json.loads(disposition_path.read_text(encoding="utf-8"))
            if disposition.get("status") == "INVALID_EVALUATION_INFRA":
                invalid.append(
                    {"eval_run_id": manifest["eval_run_id"], "reason": disposition["reason"]}
                )
                continue
        for result in matching_results:
            included.append(
                {
                    "eval_run_id": manifest["eval_run_id"],
                    "fixture_id": result["fixture_id"],
                    "scenario_result": result["scenario_result"],
                    "fixture_version": result["fixture_version"],
                    "attack_profile": manifest.get("attack_profile"),
                }
            )
            for criterion in result.get("criteria") or []:
                criterion_counts.setdefault(criterion["criterion_id"], Counter())[
                    criterion["result"]
                ] += 1
    planned = args.planned if args.planned is not None else len(included)
    aggregate = aggregate_scenario_results(
        [item["scenario_result"] for item in included], planned=planned
    )
    print(
        json.dumps(
            {
                "protocol": "AGENT_EVAL_V2",
                "filters": {
                    "fixture_id": args.fixture_id,
                    "candidate_id": args.candidate_id,
                    "fixture_version": args.fixture_version,
                    "attack_profile": args.attack_profile,
                },
                "aggregate": aggregate,
                "criterion_counts": {
                    name: dict(sorted(counts.items()))
                    for name, counts in sorted(criterion_counts.items())
                },
                "included_runs": included,
                "invalid_runs": invalid,
                "infra_attempt_count": len(invalid),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
