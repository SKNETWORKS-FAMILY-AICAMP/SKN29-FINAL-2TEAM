"""도구 결과를 JSON/JSONB에 안전하게 담기 위한 값 정규화."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any


def json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.hex()
    return str(value)


__all__ = ["json_value"]
