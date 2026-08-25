"""project_id로 한정된 프로젝트별 장기 메모리 파일 경로 접근 제어.

정본: docs/설계 및 구현/중간발표 이후/작업기록/Deep_Agents/2026-08-18_06_미들웨어_전체_설계_정리.md §3~7.

`/memories/projects/{project_id}.md`(프로젝트별 상세 메모리, `memory/backend.py`의
`_MEMORY_ROUTING_PROMPT`가 모델에게 안내하는 경로)는 실제로는 별도 Store route가
아니라 `/memories/AGENTS.md`와 같은 공유 namespace `(team_id, agent_id)` 안의
파일명일 뿐이다(`memory/backend.py`의 `build_memory_backend()` route 정의로 확인) —
팀·계정 격리는 Store namespace가 하지만, **같은 팀 안에서 프로젝트 간** 메모리
파일 격리는 코드로 보장되지 않고 프롬프트 안내에만 의존했다. 이 모듈은 그 구멍을
`FilesystemPermission`(설치된 `deepagents==0.7.5`가 실제로 지원하는 경로별
allow/deny/interrupt 규칙)으로 막는다.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deepagents.middleware.filesystem import FilesystemPermission

#: 다른 프로젝트 메모리까지 덮는 넓은 패턴. 이 패턴 자체는 `/memories/AGENTS.md`,
#: `/memories/users/preferences.md`와 겹치지 않는다(둘 다 `/memories/projects/`로
#: 시작하지 않음) — 그래서 이 두 파일의 기존 동작에는 영향이 없다.
_PROJECT_MEMORY_GLOB = "/memories/projects/**"

#: `project_id`를 glob 패턴 문자열에 그대로 보간하기 전에 검증하는 문자셋.
#: `DB/schema.sql`의 `proj.proj_id`가 `VARCHAR(5)`인 것만 확인했고 값 생성 로직
#: (허용 문자셋)까지는 확인하지 못했다 — 영숫자가 아닌 값(글롭 메타문자 `*`/`?`나
#: `/`)이 섞이면 allow 규칙이 의도보다 넓게 매치할 위험이 이론적으로 있어서,
#: 이 문자셋을 벗어나면 원래 있어선 안 되는 값으로 보고 `project_id=None`과
#: 동일하게(차단 쪽으로) 처리한다.
_SAFE_PROJECT_ID = re.compile(r"^[A-Za-z0-9]+$")


def build_filesystem_permissions(*, project_id: str | None) -> list["FilesystemPermission"]:
    """이번 세션의 `project_id`가 아닌 다른 프로젝트의 메모리 파일 접근을 막는다.

    규칙은 순서가 의미를 가진다 — `FilesystemMiddleware`(정확히는
    `deepagents.middleware.filesystem._check_fs_permission()`)는 규칙 리스트를
    **순서대로** 검사해 첫 매치를 그대로 적용한다(스코프가 좁은 쪽이 자동으로
    이기는 게 아니다 — 실제 소스로 확인). 그래서 현재 프로젝트를 허용하는 구체적인
    규칙을 항상 `/memories/projects/**` 전체를 막는 규칙보다 앞에 둔다.

    `project_id`가 `None`이거나 `_SAFE_PROJECT_ID`를 벗어나면 allow 규칙 없이
    deny 규칙만 반환한다 — 애매하면 차단하는 쪽(fail-closed)이며, 이미 있는
    `ToolPermissionError`/역할 재검사와 같은 방향이다.
    """
    from deepagents.middleware.filesystem import FilesystemPermission

    rules: list[FilesystemPermission] = []
    if project_id is not None and _SAFE_PROJECT_ID.match(project_id):
        rules.append(
            FilesystemPermission(
                operations=["read", "write"],
                paths=[f"/memories/projects/{project_id}.md"],
                mode="allow",
            )
        )
    rules.append(
        FilesystemPermission(
            operations=["read", "write"],
            paths=[_PROJECT_MEMORY_GLOB],
            mode="deny",
        )
    )
    return rules


__all__ = ["build_filesystem_permissions"]
