"""검증용 모델 호출의 provider별 동시성·분당 요청 제한."""

from __future__ import annotations

from collections import defaultdict, deque
from contextlib import contextmanager
import threading
import time

from django.conf import settings


class ProviderCapacityTimeout(TimeoutError):
    pass


class _ProviderLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._semaphores: dict[str, threading.BoundedSemaphore] = {}
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    def _semaphore(self, provider: str) -> threading.BoundedSemaphore:
        with self._lock:
            return self._semaphores.setdefault(
                provider,
                threading.BoundedSemaphore(max(1, settings.SKILL_VALIDATION_PROVIDER_MAX_CONCURRENCY)),
            )

    @contextmanager
    def slot(self, provider: str, *, deadline: float):
        semaphore = self._semaphore(provider)
        remaining = max(0.0, deadline - time.monotonic())
        if not semaphore.acquire(timeout=remaining):
            raise ProviderCapacityTimeout("모델 제공자 처리 용량을 기다리다 검증 제한 시간을 초과했습니다.")
        try:
            self._wait_for_rate(provider, deadline=deadline)
            yield
        finally:
            semaphore.release()

    def _wait_for_rate(self, provider: str, *, deadline: float) -> None:
        rpm = max(1, settings.SKILL_VALIDATION_PROVIDER_REQUESTS_PER_MINUTE)
        while True:
            now = time.monotonic()
            with self._lock:
                requests = self._requests[provider]
                while requests and now - requests[0] >= 60:
                    requests.popleft()
                if len(requests) < rpm:
                    requests.append(now)
                    return
                wait_seconds = 60 - (now - requests[0])
            if now + wait_seconds >= deadline:
                raise ProviderCapacityTimeout("모델 제공자 요청 한도를 기다리다 검증 제한 시간을 초과했습니다.")
            time.sleep(min(wait_seconds, 1.0))


provider_limiter = _ProviderLimiter()

__all__ = ["ProviderCapacityTimeout", "provider_limiter"]
