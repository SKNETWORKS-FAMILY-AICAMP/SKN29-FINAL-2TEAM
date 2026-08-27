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
ALLOWED_BASE_VERSION_IDS = {"AV035", "AV067", "AV068", "AV069"}
OWNER_ACCOUNT_ID = "UA002"
PROMPT_MARKER = "[문서 근거 완전성 v4]"
PROMPT_ADDENDUM = f"""

{PROMPT_MARKER}
- 사용자가 요청한 항목을 먼저 구분하고 최종 답변에서 각 항목을 모두 다룬다.
- 일정·범위처럼 여러 하위 항목이 있는 질문은 하위 항목을 먼저 나열하고, 각 항목의
  구체 값을 개별적으로 검색·확인한 뒤 답한다. 일부 항목만 찾은 채 전체를 확인했다고
  간주하거나 나머지가 문서에 없다고 단정하지 않는다.
- WBS·과업 일정의 세부 행을 찾을 때는 같은 일반 검색을 반복하지 않는다. 먼저 찾은
  하위 작업 명칭들과 찾으려는 열 이름(작업·공수·기간)을 한 질의에 함께 넣고 충분한
  결과 수로 검색해 세부 표 행을 확인한다.
- 사용자가 명시적으로 요청한 항목에 직접 관련된 세부 날짜·수치는 전체 합계나
  전체 기간으로 대체하지 않고 보존한다.
- 요청 범위를 벗어난 세부 정보는 단지 문서에 있다는 이유만으로 추가하지 않는다.
- 답변에 쓰는 각 사실은 문서나 도구 결과에서 그 값을 직접 확인한다. 응답 형식을
  채우기 위해 확인되지 않은 우선순위·선행 작업·시스템 상태를 추측하지 않는다.
- 최종 답변 직전에 요청받은 하위 항목별 근거와 누락 여부를 다시 점검한다.
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
    parser.add_argument(
        "--reasoning-effort",
        choices=("low", "medium", "high"),
        help="생략하면 기준 버전 값을 보존한다. 스모크 실패 후 변수 하나만 바꿀 때 사용한다.",
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
    target_reasoning_effort = args.reasoning_effort or current["reasoning_effort"]
    if (
        PROMPT_MARKER in current["system_prompt"]
        and target_reasoning_effort == current["reasoning_effort"]
    ):
        print(json.dumps({
            "status": "ALREADY_PUBLISHED",
            "agent_id": AGENT_ID,
            "agent_version_id": current["current_version_id"],
            "version": current["version"],
        }, ensure_ascii=False, indent=2))
        return 0
    if current["current_version_id"] not in ALLOWED_BASE_VERSION_IDS:
        raise RuntimeError(
            f"허용한 기준 버전은 {sorted(ALLOWED_BASE_VERSION_IDS)}인데 현재 버전은 "
            f"{current['current_version_id']}입니다. 자동 발행을 중단합니다."
        )

    candidate = {
        "name": current["name"],
        "description": current["description"],
        "system_prompt": build_candidate_prompt(current["system_prompt"]),
        "model": current["model"],
        "reasoning_effort": target_reasoning_effort,
        "max_iterations": current["max_iterations"],
        "tool_refs": current["tool_refs"],
        "subagents": current["subagents"],
    }
    if not args.apply:
        print(json.dumps({
            "status": "DRY_RUN",
            "base_version_id": current["current_version_id"],
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
