from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from .evaluators import (
    run_deepeval_answer_relevancy,
    run_ragas_faithfulness,
    run_ragas_id_context_metrics,
)
from .garak_report import summarize_garak_report
from .models import LabCase, MetricScore, load_cases
from .telemetry import PhoenixTelemetry, score_as_json
from .v2_batch import run_frozen_batch
from .v2_import import load_recent_v2_cases


def _load_project_env() -> None:
    """기존 값을 덮어쓰지 않고 프로젝트 루트 .env를 재사용한다."""
    project_root = Path(__file__).resolve().parents[3]
    load_dotenv(project_root / ".env", override=False)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OTel 평가 학습 실험실")
    sub = parser.add_subparsers(dest="command", required=True)

    trace = sub.add_parser("import-v2", help="기존 V2 결과를 요약 Trace로 표시")
    trace.add_argument("--results-root", type=Path, default=Path("outputs/eval-v2-results"))
    trace.add_argument("--limit", type=int, default=3)

    evaluate = sub.add_parser("evaluate", help="샘플을 Ragas/DeepEval로 평가")
    evaluate.add_argument("--cases", type=Path, default=Path(__file__).parents[1] / "sample_cases.json")
    evaluate.add_argument("--evaluator", choices=("deepeval", "ragas", "both"), default="deepeval")

    garak = sub.add_parser("import-garak", help="Garak report.jsonl을 Phoenix에 표시")
    garak.add_argument("report", type=Path)

    agent_garak = sub.add_parser(
        "import-agent-garak", help="격리 에이전트 Garak 재생 결과를 Phoenix에 표시"
    )
    agent_garak.add_argument("result", type=Path)

    batch = sub.add_parser("evaluate-v2-batch", help="동결 V2 48건을 보조 지표로 재채점")
    batch.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parents[1] / "artifacts" / "v2_professional_results.json",
    )
    return parser


def _emit(cases: list[LabCase], score_fn=None) -> list[dict[str, object]]:
    telemetry = PhoenixTelemetry()
    output: list[dict[str, object]] = []
    for case in cases:
        with telemetry.case_span(case) as span:
            scores: list[MetricScore] = score_fn(case) if score_fn else []
            for score in scores:
                telemetry.add_score(span, score)
            output.append({"case_id": case.case_id, "scores": [score_as_json(s) for s in scores]})
    telemetry.flush()
    return output


def main() -> int:
    _load_project_env()
    args = _parser().parse_args()
    if args.command == "import-v2":
        cases = load_recent_v2_cases(args.results_root, args.limit)
        if not cases:
            raise RuntimeError("가져올 수 있는 정상 V2 결과가 없습니다.")
        result = _emit(cases)
    elif args.command == "evaluate":
        cases = load_cases(args.cases)

        def score(case: LabCase) -> list[MetricScore]:
            values: list[MetricScore] = []
            if args.evaluator in {"deepeval", "both"}:
                values.append(run_deepeval_answer_relevancy(case))
            if args.evaluator in {"ragas", "both"}:
                values.extend(run_ragas_id_context_metrics(case))
                values.append(run_ragas_faithfulness(case))
            return values

        result = _emit(cases, score)
    elif args.command == "import-garak":
        summary, scores = summarize_garak_report(args.report)
        case = LabCase(
            case_id=args.report.stem,
            input="Garak adversarial scan",
            actual_output=json.dumps(summary, ensure_ascii=False),
            source="GARAK_REPORT_IMPORT",
            metadata=summary,
        )
        result = _emit([case], lambda _: scores)
    elif args.command == "import-agent-garak":
        payload = json.loads(args.result.read_text(encoding="utf-8"))
        cases: list[LabCase] = []
        scores_by_case: dict[str, list[MetricScore]] = {}
        for item in payload["results"]:
            case_id = f"garak-agent-safe-{item['seq']}"
            passed = bool(item["passed"])
            cases.append(
                LabCase(
                    case_id=case_id,
                    input=str(item["prompt"]),
                    actual_output=str(item["answer"]),
                    tools_called=[str(value) for value in item["tools_called"]],
                    source="GARAK_PROMPT_LOCAL_AGENT_REPLAY",
                    metadata={
                        "official_score_eligible": False,
                        "candidate_id": payload["candidate_id"],
                        "candidate_model": item["candidate_model"],
                        "business_tools_exposed": False,
                        "detector": "exact_trigger_containment",
                    },
                )
            )
            scores_by_case[case_id] = [
                MetricScore(
                    evaluator="garak",
                    metric="promptinject.HijackLongPrompt.agent_isolated",
                    score=1.0 if passed else 0.0,
                    passed=passed,
                    reason=(
                        "공격 문자열 미출력, 도구 호출 없음"
                        if passed
                        else (
                            f"attack_triggered={bool(item['attack_triggered'])}, "
                            f"tools_called={item['tools_called']}"
                        )
                    ),
                )
            ]
        result = _emit(cases, lambda case: scores_by_case[case.case_id])
    else:
        result = run_frozen_batch(args.output)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
