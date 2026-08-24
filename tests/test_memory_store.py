"""`services.agent_runtime.memory.store.get_memory_store()` — 프로세스 전역
싱글턴의 최초 연결 경합을 막는 락(2026-08-22 추가).

정본: 설정 > 스킬 화면(`SkillsTab.tsx`)이 개인/팀 스킬 목록을 `Promise.all`로
**동시에** 부르면서, 이 프로세스에서 `get_memory_store()`를 처음 부르는
순간이 겹치는 사례를 실제로 봤다 — `if _store is not None` 검사를 두 요청이
동시에 통과해 `PostgresStore.from_conn_string()`과 `.setup()`이 겹쳐 실행되며
500으로 죽었다. 여기서는 진짜 `PostgresStore` 대신 호출 횟수를 세는 가짜로
바꿔, 여러 스레드가 동시에 불러도 **연결은 딱 한 번만** 만들어지고 전부 같은
인스턴스를 받는지 확인한다.
"""

from __future__ import annotations

import threading
import time

from django.test import SimpleTestCase

import services.agent_runtime.memory.store as store_module


class _FakeStore:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def setup(self) -> None:
        self._calls.append("setup")


class _FakeConnCM:
    """`PostgresStore.from_conn_string()`이 돌려주는 컨텍스트 매니저 흉내."""

    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def __enter__(self) -> _FakeStore:
        self._calls.append("enter")
        return _FakeStore(self._calls)

    def __exit__(self, *exc_info: object) -> None:
        return None


class MemoryStoreLockTests(SimpleTestCase):
    def setUp(self) -> None:
        # 프로세스 전역 상태다 — 테스트마다 깨끗하게 시작하고, 끝나면 원복해서
        # 이 테스트 파일 뒤에 도는 다른 테스트(진짜 `get_memory_store`를 모킹해
        # 쓰는 `test_skills_service.py`/`test_skills_api.py`)에 흘러들지 않게 한다.
        self._orig_store = store_module._store
        self._orig_store_cm = store_module._store_cm
        store_module._store = None
        store_module._store_cm = None

    def tearDown(self) -> None:
        store_module._store = self._orig_store
        store_module._store_cm = self._orig_store_cm

    def test_동시에_불러도_연결은_한_번만_만든다(self) -> None:
        calls: list[str] = []
        from_conn_string_calls: list[str] = []

        def fake_from_conn_string(_conn_string: str, **_kwargs: object) -> _FakeConnCM:
            from_conn_string_calls.append(_conn_string)
            # 진짜 연결에 걸리는 시간을 흉내낸다 — 락이 없으면 이 잠깐 사이에
            # 다른 스레드도 `if _store is not None` 검사를 통과해 여기로
            # 들어온다. 락이 있으면 이 함수 전체가 락 안에서만 불린다.
            time.sleep(0.05)
            return _FakeConnCM(calls)

        import langgraph.store.postgres as postgres_module

        original = postgres_module.PostgresStore.from_conn_string
        postgres_module.PostgresStore.from_conn_string = staticmethod(fake_from_conn_string)  # type: ignore[assignment]
        try:
            from django.conf import settings

            original_url = getattr(settings, "RAW_DATABASE_URL", None)
            settings.RAW_DATABASE_URL = "postgresql://fake/for-test"
            try:
                worker_count = 8
                barrier = threading.Barrier(worker_count)
                results: list[object] = []
                results_lock = threading.Lock()

                def worker() -> None:
                    barrier.wait()  # 최대한 같은 순간에 부딪히게 한다.
                    store = store_module.get_memory_store()
                    with results_lock:
                        results.append(store)

                threads = [threading.Thread(target=worker) for _ in range(worker_count)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=5)
            finally:
                settings.RAW_DATABASE_URL = original_url
        finally:
            postgres_module.PostgresStore.from_conn_string = original  # type: ignore[assignment]

        # 락이 없으면 여러 스레드가 각자 연결을 만들어 `from_conn_string_calls`와
        # `setup` 호출이 worker 수만큼 늘어난다 — 이 값이 여기서 실제로 500을
        # 일으킨 원인이다.
        self.assertEqual(from_conn_string_calls, ["postgresql://fake/for-test"])
        self.assertEqual(calls, ["enter", "setup"])
        self.assertEqual(len(results), worker_count)
        self.assertEqual(len({id(store) for store in results}), 1)
