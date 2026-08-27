"""§8.10 "도구 stub" — 모든 업무 도구를 실제 handler와 분리한다.

정본: 03_스킬_검증_등록_설계.md §8.10. side-effect 도구만 막는 것으로는
부족하다 — 읽기 도구가 실제 문서·Jira·HR에 접근하면 실행마다 결과가
달라지고 정보가 유출될 수 있다(같은 절). 그래서 **모든** 업무 도구를 바꾼다.

실제 `ToolLoader`가 만든 진짜 `Tool`(이름·설명·schema·side_effect)을 그대로
쓰고 `handler`만 바꾼다 — schema가 운영과 달라질 걱정이 없다(진짜 그 객체를
빌려 쓸 뿐이다). `tool_stub_version`은 이 파일이 바뀔 때마다 사람이 올린다.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from services.agent_runtime.context import RuntimeContext
    from services.harness.registry import Tool

#: 이 stub 로직 자체의 버전. `tool_fixtures` 해석 규칙이나 합성 성공 응답의
#: 모양을 바꾸면 올린다 — job의 `tool_stub_version`에 그대로 남는다.
TOOL_STUB_VERSION = "v1"

FIXTURE_NOT_CONFIGURED = "FIXTURE_NOT_CONFIGURED"


@dataclasses.dataclass
class RecordedCall:
    tool_ref: str
    args: dict[str, Any]


class ToolCallRecorder:
    """한 번의 격리 실행 동안 호출된 도구를 순서대로 기록한다."""

    def __init__(self) -> None:
        self.calls: list[RecordedCall] = []

    def record(self, tool_ref: str, args: dict[str, Any]) -> None:
        self.calls.append(RecordedCall(tool_ref=tool_ref, args=dict(args)))

    def tool_refs(self) -> list[str]:
        return [c.tool_ref for c in self.calls]

    def count(self, tool_ref: str) -> int:
        return sum(1 for c in self.calls if c.tool_ref == tool_ref)


def _make_stub_handler(
    tool: "Tool", *, fixtures: list[dict[str, Any]] | None, recorder: ToolCallRecorder
):
    fixture_iter = iter(fixtures or [])

    def _stub(**kwargs: Any) -> Any:
        # 예약 키(`_TOOL_CALL_ID_KWARG` 등)는 실제 handler와 마찬가지로 그냥
        # kwargs에 섞여 들어온다 — 기록에는 남기되 stub 응답에는 영향 없다.
        recorder.record(tool.ref, kwargs)

        if not tool.side_effect:
            # 읽기 도구 — fixture가 없으면 조용히 성공한 것처럼 굴지 않는다
            # (§8.10 "fixture가 없는 읽기 호출은 FIXTURE_NOT_CONFIGURED").
            fixture = next(fixture_iter, None)
            if fixture is None:
                return {"error": FIXTURE_NOT_CONFIGURED, "tool_ref": tool.ref}
            return fixture

        # 쓰기·전송·삭제 도구 — 실제 handler를 절대 안 부른다. 합성 성공만
        # 돌려준다. 호출 자체는 이미 recorder에 남았으므로 채점은 그걸로 한다.
        return {"status": "ok", "stub": True, "tool_ref": tool.ref}

    return _stub


class EvalToolLoader:
    """`ToolLoader`와 같은 인터페이스(`load(*, tool_refs, context, agent_model)`)를
    구현하되, 반환하는 `Tool`마다 handler를 stub으로 갈아 끼운다.

    실행 한 번(테스트 케이스 하나)마다 새로 만든다 — `tool_fixtures`가
    케이스마다 다르고, `recorder`도 그 실행 하나만의 호출 기록이어야 채점이
    섞이지 않는다.
    """

    def __init__(self, *, tool_fixtures: dict[str, list[dict[str, Any]]], recorder: ToolCallRecorder) -> None:
        self._tool_fixtures = tool_fixtures
        self._recorder = recorder

    def load(
        self,
        *,
        tool_refs: tuple[str, ...],
        context: "RuntimeContext",
        agent_model: str | None = None,
    ) -> tuple["Tool", ...]:
        from services.agent_runtime.tools.loader import ToolLoader

        real_tools = ToolLoader().load(tool_refs=tool_refs, context=context, agent_model=agent_model)
        stubbed = []
        for tool in real_tools:
            handler = _make_stub_handler(
                tool, fixtures=self._tool_fixtures.get(tool.ref), recorder=self._recorder
            )
            stubbed.append(dataclasses.replace(tool, handler=handler))
        return tuple(stubbed)


__all__ = ["EvalToolLoader", "ToolCallRecorder", "RecordedCall", "FIXTURE_NOT_CONFIGURED", "TOOL_STUB_VERSION"]
