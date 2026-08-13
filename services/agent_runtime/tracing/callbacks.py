"""실행 이벤트·시간·오류·위임 관계를 로그로 기록한다.

⚠ 미구현. 완성하려면 기존 AgentRunRepository.start/finish,
ToolCallRepository.begin/end(backend/db/agent_platform.py, 이미 동작 중 —
작업목록.md 작업10 "이미 있는 것" 참고)를 이 모듈에서 호출하도록 연결한다.
부모·자식 관계는 agent_run.parent_run_id에 그대로 기록한다(02 §5.6).
"""
