"""완료된 Agent Eval V2 원시 결과를 전용 DB에 동기화하고 대조한다."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["sync-db", "reconcile-db", "sync-root", "mark-invalid"])
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--reason")
    parser.add_argument("--output-root", type=Path, default=REPO_ROOT / "outputs" / "eval-v2-results")
    return parser


def _completed_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        raise FileNotFoundError(root)
    return sorted(path for path in root.iterdir() if path.is_dir() and (path / "v2_summary.json").is_file())


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    import django
    django.setup()
    from backend.db.evaluation import V2EvaluationResultRepository
    from services.evaluation.v2_recorder import read_completed_v2_run

    if args.command == "sync-root":
        reports = []
        for run_dir in _completed_dirs(args.output_root):
            bundle = read_completed_v2_run(run_dir)
            synced = V2EvaluationResultRepository.sync_completed_run(bundle)
            checked = V2EvaluationResultRepository.reconcile_completed_run(bundle)
            reports.append({**synced, **checked})
        result = {"run_count": len(reports), "matched_count": sum(1 for item in reports if item["matched"]), "runs": reports}
        ok = result["matched_count"] == result["run_count"]
    else:
        if args.run_dir is None:
            raise ValueError("--run-dir가 필요합니다.")
        if args.command == "mark-invalid":
            if not args.reason:
                raise ValueError("--reason이 필요합니다.")
            from services.evaluation.v2_recorder import V2EvaluationRecorder
            V2EvaluationRecorder.open(args.run_dir).record_disposition(
                status="INVALID_EVALUATION_INFRA", reason=args.reason
            )
        bundle = read_completed_v2_run(args.run_dir)
        if args.command in {"sync-db", "mark-invalid"}:
            result = V2EvaluationResultRepository.sync_completed_run(bundle)
            if args.command == "mark-invalid":
                result |= V2EvaluationResultRepository.reconcile_completed_run(bundle)
        else:
            result = V2EvaluationResultRepository.reconcile_completed_run(bundle)
        ok = result.get("matched", True)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
