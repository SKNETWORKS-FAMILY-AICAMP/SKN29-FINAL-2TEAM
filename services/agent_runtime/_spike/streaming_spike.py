"""서브 에이전트 스트리밍 선행 검증 (일회성 스파이크 스크립트).

정본: docs/작업기록/Deep_Agents/2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md §15

목적 — 이것 하나만 확인한다:
    deepagents(고정 버전)에서 부모 Deep Agent + CompiledSubAgent 1개 + 도구
    1회 호출을 스트리밍했을 때, 다음 순서로 이벤트를 실시간으로 구분해서 받을
    수 있는가?

        agent_started(parent)
        subagent_started(child)
        tool_started(child)
        tool_completed(child)
        subagent_completed(child)
        result(parent)

⚠ 이 파일은 서비스 코드가 아니다. services/agent_runtime/__init__.py의 공개
인터페이스에도, 다른 어떤 모듈에도 이 파일을 import하지 않는다. 결과만 보고
지운다.

실행 전제 (2026-08-13 작성 시점 확인 사항 — 실행 전 다시 확인할 것):
  1. Python >= 3.11 (Dockerfile 기준 3.13). 개발 샌드박스는 3.10이라 여기서
     설치·실행 불가 — 로컬(.venv) 또는 동일 스펙 환경에서 돌릴 것.
  2. `pip install deepagents==0.7.5` (requirements/base.txt에 이미 pin됨).
  3. 모델 자격 증명. deepagents 자체 의존성은 langchain-anthropic·
     langchain-google-genai만 강제하고, 이 프로젝트 .env에는 OPENAI_API_KEY만
     있다(ANTHROPIC_API_KEY 없음, 2026-08-13 확인). 아래 중 하나를 고를 것:
       (a) `pip install langchain-openai` 추가 설치 후 OPENAI_API_KEY로 실행
           (project runner._default_model처럼 OpenAI 호환 base_url을 쓰는 커스텀
           모델일 수 있으니 OPENAI_BASE_URL 환경변수도 확인할 것 — 순정 OpenAI가
           아니면 응답 스키마가 다를 수 있다).
       (b) 팀의 ANTHROPIC_API_KEY를 로컬 환경변수로 따로 넣고 langchain-anthropic
           네이티브 경로로 실행(패키지 설치는 이미 pin돼 있음).
     이 스크립트는 (a)를 기본으로 가정한다 — MODEL_PROVIDER 환경변수로 전환 가능.
  4. 비용: 아주 작은 프롬프트 + 도구 1회 호출 1턴뿐이다. 그래도 실제 API 호출이
     나간다 — 무료가 아니다.

실행: `python services/agent_runtime/_spike/streaming_spike.py`
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path


def _load_dotenv_once() -> None:
    """저장소 루트 `.env`를 읽어 아직 없는 환경변수만 채운다.

    셸에서 `$env:OPENAI_API_KEY = ...`를 깜빡하고 다른 터미널에서 스크립트를
    돌리면(2026-08-13 실제로 겪음 — "Missing credentials") 매번 똑같이
    실패한다. Django도 `config/settings/base.py`에서 `.env`를 읽어 쓰므로,
    이 스크립트도 같은 파일을 직접 읽게 해서 이 실패 자체를 없앤다. 이미
    셸에 설정된 값이 있으면 그 값을 우선한다(명시적 override 허용).
    """
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if not env_path.exists():
        print(f"경고: {env_path} 를 못 찾았다 — 셸 환경변수만 쓴다.", file=sys.stderr)
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv_once()

if sys.version_info < (3, 11):
    print(
        f"이 스크립트는 Python >= 3.11이 필요하다 (현재 {sys.version}). "
        "deepagents requires-python이 >=3.11이다. 로컬 .venv(3.13)에서 실행할 것.",
        file=sys.stderr,
    )
    raise SystemExit(1)

try:
    from deepagents import CompiledSubAgent, create_deep_agent
except ImportError as exc:  # pragma: no cover
    print(
        "deepagents가 설치돼 있지 않다. `pip install deepagents==0.7.5` "
        "(requirements/base.txt에 이미 pin돼 있으니 `pip install -r requirements/base.txt`도 가능).",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc


# --- 1. 테스트 도구 하나: 부르면 시간을 반환한다(관측하기 쉽도록 부작용 없음) ---
def get_server_time() -> str:
    """현재 서버 시각을 ISO 8601 문자열로 반환한다."""
    return datetime.now().isoformat()


# --- 2. 모델. 프로젝트 .env에 맞춰 OpenAI 호환 경로를 기본으로 쓴다 --------------
def _build_model():
    provider = os.environ.get("SPIKE_MODEL_PROVIDER", "openai").lower()

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=os.environ.get("SPIKE_MODEL", "claude-3-5-haiku-latest"))

    # 기본: OpenAI 호환. langchain-openai는 requirements에 아직 안 넣었다 —
    # 이 스크립트 실행 전에 `pip install langchain-openai`를 따로 할 것.
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:  # pragma: no cover
        print(
            "langchain-openai가 없다. `pip install langchain-openai` 하거나 "
            "SPIKE_MODEL_PROVIDER=anthropic 환경변수로 전환할 것.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    kwargs = {"model": os.environ.get("SPIKE_MODEL", "gpt-4o-mini")}
    base_url = os.environ.get("OPENAI_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def main() -> None:
    model = _build_model()

    # --- 3. 자식: 서버 시간 도구 하나만 가진 최소 Deep Agent ---------------------
    child_graph = create_deep_agent(
        model=model,
        system_prompt="사용자가 시간을 물으면 get_server_time 도구로 답하라.",
        tools=[get_server_time],
    )

    child = CompiledSubAgent(
        name="time_teller",
        description="현재 서버 시각을 물어볼 때 사용한다.",
        runnable=child_graph,
    )

    # --- 4. 부모: 자식 하나를 서브 에이전트로 가진 Deep Agent -------------------
    parent = create_deep_agent(
        model=model,
        system_prompt=(
            "사용자가 지금 몇 시인지 물으면 반드시 time_teller 서브 에이전트에게 "
            "위임하라. 직접 답하지 마라."
        ),
        subagents=[child],
    )

    print("=== 스파이크 실행 시작 ===")
    print("기대 순서: agent_started(parent) -> subagent_started(child) -> "
          "tool_started(child) -> tool_completed(child) -> "
          "subagent_completed(child) -> result(parent)\n")

    observed: list[str] = []

    # 02 §15가 검토하라고 지목한 두 방식 중 우선 LangGraph 저수준 스트림으로
    # 시도한다. stream_events(version="v3")가 있으면 그쪽으로 바꿔서 한 번 더
    # 비교해볼 것 — 결과를 02 §15에 기록한다.
    for event in parent.stream(
        {"messages": [{"role": "user", "content": "지금 몇 시야?"}]},
        stream_mode=["updates", "messages", "custom"],
        subgraphs=True,
    ):
        # 실제 event 구조는 실행해보기 전에는 모른다 — 여기서는 관측용으로
        # 통째로 찍고, observed에는 "무엇을 봤는지" 사람이 육안으로 분류해
        # 채워 넣는다(자동 분류는 이 스파이크의 목적이 아니다. events.py의
        # EventMapper가 이 관찰 결과를 바탕으로 나중에 자동 분류를 구현한다).
        print("--- raw event ---")
        print(repr(event)[:2000])

    print("\n=== 스파이크 실행 끝 ===")
    print(
        "위 raw event들을 보고 02 §15.1의 6단계 순서를 실시간으로 구분할 수 있는지 "
        "사람이 눈으로 판정할 것. 판정 결과를 02 §15에 한 문단으로 기록하고:\n"
        "  - 순서를 실시간으로 얻을 수 있으면 -> events.py의 EventMapper를 이 event 구조에 "
        "맞춰 구현.\n"
        "  - 못 얻으면 -> events.py의 EVENT_SUBAGENT_*_FALLBACK 두 단계로 이벤트 스펙을 "
        "낮추고, 02 문서의 §14 이벤트 계약도 그에 맞춰 수정할 것."
    )


if __name__ == "__main__":
    main()
