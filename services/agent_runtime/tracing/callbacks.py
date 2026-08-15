"""이 파일은 의도적으로 비어 있다.

`agent_run`/`tool_call` 적재는 `tracing/__init__.py`의 `trace_events()`가
전부 한다(이벤트 스트림을 감싸는 방식) — 별도의 콜백 훅이 필요 없었다.
LangChain/langgraph의 `BaseCallbackHandler` 같은 콜백 기반 연결이 나중에
필요해지면(예: 이벤트 스트림에 없는 더 세밀한 신호를 잡아야 할 때) 그때
이 파일을 채운다.
"""
