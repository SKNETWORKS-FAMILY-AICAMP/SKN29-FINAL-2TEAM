"""수동 Agent 평가 실행의 v0 산출물을 기록한다."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.evaluation import EvaluationRecorder, read_completed_run  # noqa: E402


def _read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON 객체가 필요합니다: {path}")
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    start = commands.add_parser("start", help="새 평가 실행을 시작한다")
    start.add_argument("--output-root", required=True, type=Path)
    start.add_argument("--manifest", required=True, type=Path)

    append = commands.add_parser("append-case", help="사례 결과 한 건을 추가한다")
    append.add_argument("--run-dir", required=True, type=Path)
    append.add_argument("--case-result", required=True, type=Path)

    finalize = commands.add_parser("finalize", help="요약과 보고서를 생성한다")
    finalize.add_argument("--run-dir", required=True, type=Path)
    finalize.add_argument("--status", required=True)
    finalize.add_argument("--limitation", action="append", default=[])

    sync_db = commands.add_parser(
        "sync-db", help="종료된 로컬 평가 실행을 프로젝트 DB에 동기화한다"
    )
    sync_db.add_argument("--run-dir", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "start":
        recorder = EvaluationRecorder.start(
            output_root=args.output_root,
            manifest=_read_json(args.manifest),
        )
    elif args.command == "sync-db":
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
        import django

        django.setup()
        from backend.db.evaluation import EvaluationResultRepository

        manifest, case_results, summary = read_completed_run(args.run_dir)
        result = EvaluationResultRepository.sync_completed_run(
            manifest=manifest,
            case_results=case_results,
            summary=summary,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    else:
        recorder = EvaluationRecorder.open(args.run_dir)
        if args.command == "append-case":
            recorder.append_case(_read_json(args.case_result))
        else:
            recorder.finalize(status=args.status, limitations=args.limitation)
    print(recorder.run_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
