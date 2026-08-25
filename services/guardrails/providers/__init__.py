"""등록된 외부 가드레일을 실제로 호출하는 자리.

공급자마다 프로토콜이 다르지만(REST · SigV4 · 설치형 라이브러리) **부르는 쪽은
하나만 안다** — `verify()` 로 붙는지 보고, `check()` 로 검사한다.

정본: docs/설계 및 구현/중간발표 이후/작업기록/2026-08-20_가드레일_조사와_실측.md §8
"""

from .base import GuardrailVerdict, ProviderError, VerifyResult, check, verify

__all__ = ["GuardrailVerdict", "ProviderError", "VerifyResult", "check", "verify"]
