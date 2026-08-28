"""실제 모델에 전체 Registry를 제공해 단일 Tool 선택 정확도를 측정한다."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402

from services.harness.registry import ALWAYS_ON_TOOL_REFS, BUILTIN_TOOLS  # noqa: E402
from services.harness.runner import DEFAULT_MODEL  # noqa: E402

SYSTEM = (
    "사용자 요청을 처리하는 데 가장 적절한 도구가 필요하면 정확히 하나만 호출하세요. "
    "도구 없이 답할 수 있으면 어떤 도구도 호출하지 말고 NO_TOOL만 답하세요. "
    "이 평가는 선택만 확인하므로 실제 업무 결과를 만들거나 추가 질문을 하지 마세요."
)


def _tool_specs() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.ref,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }
        for tool in BUILTIN_TOOLS.values()
        if tool.ref not in ALWAYS_ON_TOOL_REFS
    ]


def _run_case(model, case: dict[str, Any]) -> dict[str, Any]:
    try:
        message = model.invoke([("system", SYSTEM), ("human", case["query"])])
        calls = list(getattr(message, "tool_calls", []) or [])
        selected = calls[0].get("name") if len(calls) == 1 else None
        error = None if len(calls) <= 1 else f"MULTIPLE_TOOL_CALLS:{len(calls)}"
    except Exception as exc:  # 결과 파일에 클래스만 남기고 key·endpoint 문자열은 숨긴다.
        selected = None
        error = exc.__class__.__name__
    expected = case.get("expected_tool")
    return {
        "id": case["id"],
        "kind": case["kind"],
        "expected_tool": expected,
        "selected_tool": selected,
        "passed": error is None and selected == expected,
        "error": error,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        default=PROJECT_ROOT / "tests/fixtures/builtin_tools/routing_cases.v1.json",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("라우팅 평가 cases가 필요합니다.")
    model = ChatOpenAI(
        model=args.model,
        openai_api_key=settings.OPENAI_API_KEY,
        use_responses_api=True,
    ).bind_tools(_tool_specs())

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.concurrency, 8))) as executor:
        pending = {executor.submit(_run_case, model, case): case["id"] for case in cases}
        for future in as_completed(pending):
            results.append(future.result())
    results.sort(key=lambda item: item["id"])

    by_kind = {}
    for kind in sorted({case["kind"] for case in cases}):
        selected = [result for result in results if result["kind"] == kind]
        by_kind[kind] = {
            "passed": sum(result["passed"] for result in selected),
            "total": len(selected),
        }
    report = {
        "dataset_id": dataset.get("dataset_id"),
        "dataset_version": dataset.get("version"),
        "model": args.model,
        "tool_count": len(_tool_specs()),
        "passed": sum(result["passed"] for result in results),
        "total": len(results),
        "by_kind": by_kind,
        "results": results,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
