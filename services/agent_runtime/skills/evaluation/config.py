"""§8.6 "생성은 플랫폼 설정 SKILL_EVAL_AUTHOR_MODEL, 의미 검토는
SKILL_EVAL_REVIEWER_MODEL을 사용한다"의 그 설정값.

**`.env`가 아니라 코드에 둔다** — `services/harness/runner.py`의 `DEFAULT_MODEL`과
같은 이유("환경마다 다른 모델로 도는 것을 막는다", 그 모듈 주석). 지금은 둘 다
플랫폼 기본 모델을 가리키지만, 자리를 분리해 두면 나중에 "생성은 싸게, 검토는
정확하게"처럼 갈라도 호출부(생성기/의미 검토기) 코드는 안 바뀐다.
"""

from __future__ import annotations

from services.harness.runner import DEFAULT_EFFORT, DEFAULT_MODEL
from django.conf import settings

SKILL_EVAL_AUTHOR_MODEL = DEFAULT_MODEL
#: §8.6 "생성 temperature는 0.4 이하" — reasoning effort와는 다른 축이지만,
#: 이 프로젝트의 모델 팩토리는 temperature가 아니라 reasoning_effort로 추론
#: 강도를 조절한다(`services/agent_runtime/models/factory.py`). 생성은 다양성이
#: 필요하므로 기본값을 그대로 쓰고, 검토는 결정적이어야 하므로 아래 reviewer
#: effort를 별도로 낮게 잡을 수 있게 자리를 분리한다.
SKILL_EVAL_AUTHOR_EFFORT = DEFAULT_EFFORT

SKILL_EVAL_REVIEWER_MODEL = DEFAULT_MODEL
#: §8.6 "reviewer는 0으로 고정한다" — 이 프로젝트에 temperature=0 설정이 없어
#: reasoning_effort로 가장 가까운 값(가장 결정적인 단계)을 쓴다.
SKILL_EVAL_REVIEWER_EFFORT = "low"

#: 개별 실행 timeout(§8.12). 라우팅 테스트 반복 하나, 행동 테스트 대표 케이스
#: 하나에 공통으로 적용한다.
EVAL_SINGLE_RUN_TIMEOUT_SECONDS = settings.SKILL_EVAL_SINGLE_RUN_TIMEOUT_SECONDS

#: 워커 안에서 동시에 진행할 평가 실행 수(§8.12 "워커 내부 동시 실행은 기본 6개").
EVAL_CONCURRENCY = settings.SKILL_EVAL_CONCURRENCY

#: job 하나(질문 생성부터 채점까지)의 전체 timeout(§8.8/§8.12 "전체 timeout 5분").
EVAL_JOB_TIMEOUT_SECONDS = settings.SKILL_EVAL_JOB_TIMEOUT_SECONDS

#: DB에 등록하지 않는 평가 전용 draft 에이전트의 모델 호출 상한. 사용자의
#: 채팅 에이전트 설정과 분리해야 검증 job이 채팅 설정을 바꾸거나 상속하지 않는다.
EVAL_AGENT_MAX_ITERATIONS = settings.SKILL_EVAL_AGENT_MAX_ITERATIONS

__all__ = [
    "SKILL_EVAL_AUTHOR_MODEL",
    "SKILL_EVAL_AUTHOR_EFFORT",
    "SKILL_EVAL_REVIEWER_MODEL",
    "SKILL_EVAL_REVIEWER_EFFORT",
    "EVAL_SINGLE_RUN_TIMEOUT_SECONDS",
    "EVAL_CONCURRENCY",
    "EVAL_JOB_TIMEOUT_SECONDS",
    "EVAL_AGENT_MAX_ITERATIONS",
]
