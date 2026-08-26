"""「스킬」 API 표현.

`services.agent_runtime.skills.service`가 이미 프론트 계약(`api/skills.ts`의
`Skill` 인터페이스)과 같은 모양의 dict를 돌려주므로, 여기서는 그대로
내보낸다 — 다시 만들면 두 곳이 어긋날 수 있는 값을 하나 더 만드는 셈이다.
"""

from typing import Any


def skill_response(row: dict[str, Any], *, account_id: str | None = None) -> dict[str, Any]:
    response = {
        "skill_id": row["skill_id"],
        "name": row["name"],
        "description": row["description"],
        "updated_at": row.get("updated_at"),
        "enabled": row.get("enabled", True),
        "shared_by_me": bool(
            account_id and row.get("shared_by_account_id") == account_id
        ),
        "imported_from_team": bool(row.get("imported_from_team_id")),
        "imported_by_me": bool(row.get("imported_by_me", False)),
        "can_delete": bool(row.get("can_delete", False)),
    }
    if "body" in row:
        response["body"] = row["body"]
    return response
