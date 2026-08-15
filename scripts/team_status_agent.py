"""팀 현황 도우미 — 실제 Chat 실행 경로 그대로, 터미널에서 대화하며 도구 호출을 본다.

Builder에 저장하지 않는다(`agents`/`agent_versions` 테이블은 작업자 A 소관 —
계약 문서 §17.1). 대신 `AgentDefinitionLoader.from_draft()`로 이 프로세스
안에서만 존재하는 실행 정의(draft)를 만들고, `services.agent_runtime
.build_default_executor()`(Chat API가 실제로 쓰는 바로 그 조립 — apps/chat
/api_views.py 참고)로 돌린다. 즉 Builder Test Run이 아니라 **진짜 Chat 실행과
동일한 경로**다 — 프롬프트 조립(RuntimePromptAssembler), RBAC 필터링, 호출
상한 미들웨어까지 전부 실물 그대로 탄다.

에이전트 정의:
  이름        팀 현황 도우미
  설명        프로젝트·문서·팀원 현황을 종합해서 답하는 에이전트
  행동 지시   프로젝트·문서·팀원 현황 내용에 대해 답해줘.
  모델        gpt-5.6-luna (OpenAI, 실제 모델 — ModelConfigResolver가
              "claude-" 접두사가 아니면 OpenAI 브랜치로 라우팅)
  도구        project_list(프로젝트 조회), document_list(문서 목록),
              people_list(팀원 조회), workload_report(부하 리포트),
              jira_get_issues(Jira 이슈 조회) — 전부 side_effect=False(읽기
              전용)라 role 제한 없이 leader/member 모두 쓸 수 있다.

실행 방법(로컬, 저장소 루트에서 — 실제 DB/OpenAI 네트워크가 있어야 한다):
    DJANGO_SETTINGS_MODULE=config.settings.local python3 scripts/team_status_agent.py

시작하면 로그인 이메일을 물어본다 — 그 계정의 실제 team_id/role로 실행해야
project_list/people_list 등이 진짜 데이터를 돌려준다(가짜 team_id로는 전부
빈 목록이라 이 테스트의 의미가 없다). 비밀번호는 묻지 않는다 — 로컬 DB를
직접 신뢰하는 스크립트라 로그인 API를 타지 않고 계정을 바로 조회한다(계정을
가장할 수 있는 사람은 이미 이 DB에 직접 접근할 수 있는 사람뿐이다).

질문을 입력하면 실행 중 나오는 이벤트(agent_started/tool_started/
tool_completed/subagent_started/subagent_completed/result/error)를 그대로
찍는다 — 어떤 도구가 언제 불리는지 그 자리에서 보인다. `exit`/`quit`/빈
줄로 종료. 같은 세션 안에서는 대화 이력도 이어간다(conversation_messages).
"""

from __future__ import annotations

import os
import sys
import uuid

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402

from apps.accounts.serializers import account_role  # noqa: E402
from backend.db.repositories import AccountRepository  # noqa: E402
from services.agent_runtime.context import RuntimeContext  # noqa: E402

DRAFT = {
    "name": "팀 현황 도우미",
    "description": "프로젝트·문서·팀원 현황을 종합해서 답하는 에이전트",
    "system_prompt": "프로젝트·문서·팀원 현황 내용에 대해 답해줘.",
    "model": "gpt-5.6-luna",
    "reasoning_effort": "",
    "max_iterations": 8,
    "tool_refs": [
        "project_list",
        "document_list",
        "people_list",
        "workload_report",
        "jira_get_issues",
    ],
}


def _resolve_context(email: str) -> RuntimeContext:
    account = AccountRepository.find_credentials(email)
    if account is None:
        raise SystemExit(f"[중단] 해당 이메일의 계정을 찾을 수 없습니다: {email}")

    account_id = account["account_id"]
    profile = AccountRepository.get_profile(account_id)
    team_id = AccountRepository.team_id(account_id)
    if not team_id:
        raise SystemExit(f"[중단] '{email}' 계정이 아직 팀에 속해 있지 않습니다.")

    role = account_role(profile)
    print(f"[계정] {email} (account_id={account_id}, team_id={team_id}, role={role})")

    return RuntimeContext(
        account_id=account_id,
        team_id=team_id,
        role=role,
        run_id=str(uuid.uuid4()),
    )


def _print_event(event: dict) -> str | None:
    """이벤트를 그대로 찍고, 최종 텍스트면 반환한다."""
    etype = event.get("type")
    if etype == "tool_started":
        # events.py EventMapper: tool_started는 tool_ref만 싣는다(호출 인자는
        # 이 이벤트 모양에 없음 — 계약 문서 §14.1 그대로).
        print(f"  🔧 tool_started  {event.get('tool_ref')}")
    elif etype == "tool_completed":
        print(f"  ✅ tool_completed {event.get('tool_ref')}")
    elif etype == "subagent_started":
        print(f"  🤝 subagent_started {event.get('subagent_name')} (alias 기반 위임)")
    elif etype == "subagent_completed":
        print(f"  🤝 subagent_completed {event.get('subagent_name')} status={event.get('status')}")
    elif etype == "agent_started":
        print(f"[시작] run_id={event.get('run_id')}")
    elif etype == "result":
        print(f"[결과] {event.get('text')}")
        return event.get("text")
    elif etype == "error":
        print(f"[에러] {event.get('error_code')}: {event.get('message')}")
    else:
        print(f"  · {event}")
    return None


def main() -> int:
    if not str(getattr(settings, "OPENAI_API_KEY", "") or "").strip():
        print("[블로킹] .env의 OPENAI_API_KEY가 비어 있다.")
        return 1

    email = input("로그인 이메일: ").strip()
    context = _resolve_context(email)

    # 지연 import — services.agent_runtime의 PEP-562 규칙(패키지 __init__.py
    # 주석 참고): build_default_executor를 실제로 쓰는 시점에만 deepagents를
    # 끌어온다.
    from services.agent_runtime import build_default_executor

    executor = build_default_executor()

    conversation_messages: list[dict] = []
    print("\n질문을 입력하세요. 종료하려면 빈 줄 또는 exit/quit.\n")

    while True:
        try:
            user_input = input("질문> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input or user_input.lower() in {"exit", "quit"}:
            break

        print("=== 실행 시작 ===")
        final_text = None
        for event in executor.run(
            agent_id=None,
            agent_version_id=None,
            user_input=user_input,
            context=context,
            draft=DRAFT,
            conversation_messages=conversation_messages,
        ):
            text = _print_event(event)
            if text:
                final_text = text
        print("=== 실행 종료 ===\n")

        conversation_messages.append({"role": "user", "content": user_input})
        if final_text:
            conversation_messages.append({"role": "assistant", "content": final_text})

    return 0


if __name__ == "__main__":
    sys.exit(main())
