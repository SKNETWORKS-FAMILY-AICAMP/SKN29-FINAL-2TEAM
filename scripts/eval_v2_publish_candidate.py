"""AG004의 V2 개선 Candidate를 기존 버전을 덮지 않고 발행한다."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

AGENT_ID = "AG004"
BASE_VERSION_ID = "AV035"
OWNER_ACCOUNT_ID = "UA002"
PROMPT_MARKER = "[문서 종합 완전성 v2]"
PROMPT_ADDENDUM = f"""

{PROMPT_MARKER}
- 사용자가 요청한 항목을 먼저 구분하고 최종 답변에서 각 항목을 모두 다룬다.
- 사용자가 명시적으로 요청한 항목에 직접 관련된 세부 날짜·수치는 전체 합계나
  전체 기간으로 대체하지 않고 보존한다.
- 요청 범위를 벗어난 세부 정보는 단지 문서에 있다는 이유만으로 추가하지 않는다.
- 응답 형식을 채우기 위해 문서나 도구 결과에서 확인되지 않은 우선순위·선행 작업·
  시스템 상태를 추측하지 않는다.
- 문서의 담당 주체·고유명칭·조직명은 의미를 바꾸어 축약하지 않고 원문 표현을 보존한다.
""".rstrip()


def build_candidate_prompt(base_prompt: str) -> str:
    prompt = (base_prompt or "").rstrip()
    if PROMPT_MARKER in prompt:
        return prompt
    return f"{prompt}{PROMPT_ADDENDUM}" if prompt else PROMPT_ADDENDUM.lstrip()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="생략하면 변경 예정 내용만 출력하고 DB에는 발행하지 않는다.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    import django

    django.setup()
    from backend.db.agent_platform import AgentVersionCrudRepository

    current = AgentVersionCrudRepository.get(
        agent_id=AGENT_ID, account_id=OWNER_ACCOUNT_ID
    )
    if PROMPT_MARKER in current["system_prompt"]:
        print(json.dumps({
            "status": "ALREADY_PUBLISHED",
            "agent_id": AGENT_ID,
            "agent_version_id": current["current_version_id"],
            "version": current["version"],
        }, ensure_ascii=False, indent=2))
        return 0
    if current["current_version_id"] != BASE_VERSION_ID:
        raise RuntimeError(
            f"예상한 기준 버전은 {BASE_VERSION_ID}인데 현재 버전은 "
            f"{current['current_version_id']}입니다. 자동 발행을 중단합니다."
        )

    candidate = {
        "name": current["name"],
        "description": current["description"],
        "system_prompt": build_candidate_prompt(current["system_prompt"]),
        "model": current["model"],
        "reasoning_effort": current["reasoning_effort"],
        "max_iterations": current["max_iterations"],
        "tool_refs": current["tool_refs"],
        "subagents": current["subagents"],
    }
    if not args.apply:
        print(json.dumps({
            "status": "DRY_RUN",
            "base_version_id": BASE_VERSION_ID,
            "candidate": candidate,
        }, ensure_ascii=False, indent=2, default=str))
        return 0

    published = AgentVersionCrudRepository.publish(
        agent_id=AGENT_ID,
        account_id=OWNER_ACCOUNT_ID,
        fields={key: candidate[key] for key in (
            "name", "description", "system_prompt", "model",
            "reasoning_effort", "max_iterations",
        )},
        tool_refs=candidate["tool_refs"],
        subagents=candidate["subagents"],
    )
    print(json.dumps({
        "status": "PUBLISHED",
        "agent_id": AGENT_ID,
        "agent_version_id": published["current_version_id"],
        "version": published["version"],
        "model": published["model"],
        "reasoning_effort": published["reasoning_effort"],
        "tool_refs": published["tool_refs"],
        "prompt_marker": PROMPT_MARKER,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
