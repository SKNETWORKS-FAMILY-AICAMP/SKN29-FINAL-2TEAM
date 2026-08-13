"""위험 도구 실행 전 사람 승인과 실행 재개 처리.

MVP 범위 밖(01 §11). 지금 Chat에 이미 있는 승인 게이트(awaiting_confirmation ->
confirm -> resume, services/harness/runner.py)가 이 역할을 하고 있다 — Deep
Agent 런타임으로 전환할 때 이 흐름을 그대로 옮길지, deepagents의 HITL 패턴으로
바꿀지는 아직 결정 안 됐다. 결정 전까지는 harness의 기존 승인 게이트를
대체하지 않는다.
"""
