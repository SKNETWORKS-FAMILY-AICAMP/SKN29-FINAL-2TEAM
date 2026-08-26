"""`services.agent_runtime.checkpoint.checkpointer.get_checkpointer()` — 프로세스
전역 싱글턴의 최초 연결 경합을 막는 락(2026-08-25 추가).

`services/agent_runtime/memory/store.py`(장기 메모리 `PostgresStore`)가 2026-08-22에
겪은 것과 똑같은 종류의 경합 — 여러 스레드가 이 프로세스에서 처음으로
`get_checkpointer()`를 부르는 순간이 겹치면 `if _checkpointer is not None` 검사를
둘 다 통과해 `PostgresSaver.from_conn_string()`과 `.setup()`이 동시에 실행될 수
있다. `test_memory_store.py`와 같은 방식으로, 진짜 `PostgresSaver` 대신 호출
횟수를 세는 가짜로 바꿔 여러 스레드가 동시에 불러도 연결은 딱 한 번만 만들어지고
전부 같은 인스턴스를 받는지 확인한다.
"""

from __future__ import annotations

import threading
import time

from django.test import SimpleTestCase

import services.agent_runtime.checkpoint.checkpointer as checkpointer_module


class _FakeCheckpointer:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def setup(self) -> None:
        self._calls.append("setup")


class _FakeConnCM:
    """`PostgresSaver.from_conn_string()`이 돌려주는 컨텍스트 매니저 흉내."""

    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def __enter__(self) -> _FakeCheckpointer:
        self._calls.append("enter")
        return _FakeCheckpointer(self._calls)

    def __exit__(self, *exc_info: object) -> None:
        return None


class CheckpointerLockTests(SimpleTestCase):
    def setUp(self) -> None:
        # 프로세스 전역 상태다 — 테스트마다 깨끗하게 시작하고, 끝나면 원복해서
        # 이 테스트 뒤에 도는 다른 테스트에 흘러들지 않게 한다.
        self._orig_checkpointer = checkpointer_module._checkpointer
        self._orig_checkpointer_cm = checkpointer_module._checkpointer_cm
        checkpointer_module._checkpointer = None
        checkpointer_module._checkpointer_cm = None

    def tearDown(self) -> None:
        checkpointer_module._checkpointer = self._orig_checkpointer
        checkpointer_module._checkpointer_cm = self._orig_checkpointer_cm

    def test_동시에_불러도_연결은_한_번만_만든다(self) -> None:
        calls: list[str] = []
        from_conn_string_calls: list[str] = []

        def fake_from_conn_string(_conn_string: str, **_kwargs: object) -> _FakeConnCM:
            from_conn_string_calls.append(_conn_string)
            # 진짜 연결에 걸리는 시간을 흉내낸다 — 락이 없으면 이 잠깐 사이에
            # 다른 스레드도 `if _checkpointer is not None` 검사를 통과해 여기로
            # 들어온다. 락이 있으면 이 함수 전체가 락 안에서만 불린다.
            time.sleep(0.05)
            return _FakeConnCM(calls)

        import langgraph.checkpoint.postgres as postgres_module

        original = postgres_module.PostgresSaver.from_conn_string
        postgres_module.PostgresSaver.from_conn_string = staticmethod(fake_from_conn_string)  # type: ignore[assignment]
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
                    checkpointer = checkpointer_module.get_checkpointer()
                    with results_lock:
                        results.append(checkpointer)

                threads = [threading.Thread(target=worker) for _ in range(worker_count)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=5)
            finally:
                settings.RAW_DATABASE_URL = original_url
        finally:
            postgres_module.PostgresSaver.from_conn_string = original  # type: ignore[assignment]

        # 락이 없으면 여러 스레드가 각자 연결을 만들어 `from_conn_string_calls`와
        # `setup` 호출이 worker 수만큼 늘어난다 — 이 값이 실제로 500을 일으킨
        # 원인(memory/store.py 쪽 사례)과 같은 형태다.
        self.assertEqual(from_conn_string_calls, ["postgresql://fake/for-test"])
        self.assertEqual(calls, ["enter", "setup"])
        self.assertEqual(len(results), worker_count)
        self.assertEqual(len({id(checkpointer) for checkpointer in results}), 1)
