"""요청자와 실행 환경을 담는 불변 컨텍스트."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AccountRole = Literal["leader", "member"]


@dataclass(frozen=True)
class RuntimeContext:
    account_id: str
    team_id: str
    role: AccountRole

    session_id: str | None = None
    project_id: str | None = None

    run_id: str | None = None
    parent_run_id: str | None = None
