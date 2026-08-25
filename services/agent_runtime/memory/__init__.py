"""장기 메모리(에이전트가 세션을 넘어 기억하는 것) — deepagents `memory=`/`backend=`/`store=` 배선.

단기 메모리(세션 안에서의 대화 이력)는 여기서 다루지 않는다 — 이 앱은 이미
`chat_message` 테이블에 대화를 저장하고 `apps/chat/api_views.py`가 매 호출마다
이전 메시지를 다시 실어 보낸다(LangGraph의 checkpointer/thread_id 방식이 아니라
이 저장소 자체 방식). deepagents 관점의 "short-term"(단일 실행 안의 스크래치
공간)은 기본 `StateBackend`가 이미 공짜로 제공하므로 이 패키지가 따로 손댈 게
없다 — `build_memory_backend()`의 `default=StateBackend()`가 그 자리다.

2026-08-15, 지훈 확인 후 착수(원래 계약 문서 §2 확정 원칙 8번 "Memory는 MVP에서
비활성화"를 뒤집는 결정 — `docs/설계 및 구현/중간발표 이후/작업기록/Deep_Agents/2026-08-15_02_장기메모리_설계.md` 참고).
"""
