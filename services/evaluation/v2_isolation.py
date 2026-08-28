"""S10/S11 DEV 실행에서 운영 저장소를 건드리지 않는 격리 provider."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore


class EvalMemoryProvider:
    """운영 ``MemoryProvider``와 같은 인터페이스를 인메모리 Store로 제공한다."""

    def __init__(self) -> None:
        self._store = InMemoryStore()

    @staticmethod
    def namespace(*, team_id: str, agent_id: str, account_id: str) -> tuple[str, str, str]:
        return (team_id, agent_id, account_id)

    def paths(self) -> list[str]:
        from services.agent_runtime.memory.backend import memory_paths

        return memory_paths()

    def backend(
        self,
        *,
        team_id: str,
        agent_id: str,
        account_id: str,
        extra_routes: dict[str, Any] | None = None,
    ):
        from services.agent_runtime.memory.backend import build_memory_backend

        backend = build_memory_backend(
            team_id=team_id,
            agent_id=agent_id,
            account_id=account_id,
            extra_routes=extra_routes,
        )
        for route in backend.routes.values():
            if getattr(route, "store", None) is None:
                route.store = self._store
        return backend

    def store(self) -> InMemoryStore:
        return self._store

    def system_prompt(self) -> str:
        from services.agent_runtime.memory.backend import memory_system_prompt

        return memory_system_prompt()

    def seed_preferences(
        self, *, team_id: str, agent_id: str, account_id: str, content: str
    ) -> None:
        from deepagents.backends import StoreBackend

        StoreBackend(
            namespace=lambda _runtime: self.namespace(
                team_id=team_id, agent_id=agent_id, account_id=account_id
            ),
            store=self._store,
        ).write("/preferences.md", content)

    def preference_content(
        self, *, team_id: str, agent_id: str, account_id: str
    ) -> str | None:
        item = self._store.get(
            self.namespace(team_id=team_id, agent_id=agent_id, account_id=account_id),
            "/preferences.md",
        )
        if item is None:
            return None
        return str(item.value.get("content") or "")

    def delete_preferences(self, *, team_id: str, agent_id: str, account_id: str) -> None:
        self._store.delete(
            self.namespace(team_id=team_id, agent_id=agent_id, account_id=account_id),
            "/preferences.md",
        )


class EvalCheckpointProvider:
    """S10/S11 실행끼리만 공유되는 인메모리 LangGraph checkpointer."""

    def __init__(self) -> None:
        self._saver = MemorySaver()

    def get(self) -> MemorySaver:
        return self._saver

    def delete_thread(self, thread_id: str) -> None:
        self._saver.delete_thread(thread_id)

    def seed_messages(self, runtime: Any, *, thread_id: str, messages: list[str]) -> None:
        runtime.update_state(
            {"configurable": {"thread_id": thread_id}},
            {"messages": [HumanMessage(content=message) for message in messages]},
        )

    def contains_text(self, *, thread_id: str, text: str) -> bool:
        checkpoint = self._saver.get({"configurable": {"thread_id": thread_id}})
        if checkpoint is None:
            return False
        return text in json.dumps(checkpoint, ensure_ascii=False, default=str)


__all__ = ["EvalCheckpointProvider", "EvalMemoryProvider"]
