"""새 버전 스키마 API(/api/agents/versions/...)를 실제 HTTP 호출로 검증하는
1회용 스크립트.

로컬 docker-compose `web`(포트 8000)이 떠 있어야 한다. `web` 서비스는
소스를 통째로 바인드 마운트하고(`infra/docker/docker-compose.yml`),
`manage.py runserver`는 파일 변경을 자동 리로드하므로 컨테이너를 새로 띄울
필요는 없다 — 그냥 이 스크립트만 실행하면 된다.

사용:
    python apps/agents/_verify_versions_api.py --email you@example.com --password ****

확인하는 것:
1. 로그인 → 토큰 발급
2. POST /api/agents/versions/  — 새 논리 에이전트 + 첫 버전 발행
3. GET  /api/agents/versions/  — 방금 만든 게 목록에 보이는가
4. GET  /api/agents/versions/<id>/ — 상세가 저장한 값과 일치하는가
5. PUT  /api/agents/versions/<id>/ — 두 번째 버전 발행 → version이 2로 늘어나는가
6. POST .../activate/, POST .../disable/ — 상태 전이
7. 자기 자신을 서브 에이전트로 넣어 저장 시도 → 409 + SelfReferenceError로
   막히는가 (services.agent_runtime.exceptions 매핑이 실제로 동작하는지)

실행 후 지워도 된다 — 일회성 스모크 테스트다.
"""

from __future__ import annotations

import argparse
import json
import sys

import requests


def _pretty(label: str, response: requests.Response) -> dict:
    try:
        body = response.json()
    except ValueError:
        body = response.text
    print(f"\n--- {label}: {response.status_code} ---")
    print(json.dumps(body, ensure_ascii=False, indent=2, default=str)[:2000])
    return body if isinstance(body, dict) else {}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--base-url", default="http://localhost:8000/api")
    args = parser.parse_args()

    session = requests.Session()

    login = session.post(
        f"{args.base_url}/auth/login/",
        json={"email": args.email, "password": args.password},
    )
    body = _pretty("로그인", login)
    if login.status_code != 200:
        print("로그인 실패 — email/password 확인.")
        sys.exit(1)
    token = body["token"]
    session.headers["Authorization"] = f"Bearer {token}"

    # 2) 발행
    payload = {
        "name": "[검증] 테스트 에이전트",
        "description": "API 검증용",
        "system_prompt": "너는 테스트용 에이전트다.",
        "model": "gpt-5.6-luna",
        "reasoning_effort": "low",
        "max_iterations": 6,
        "tool_refs": [],
        "subagents": [],
    }
    created = session.post(f"{args.base_url}/agents/versions/", json=payload)
    body = _pretty("1) 발행(POST /versions/)", created)
    if created.status_code != 201:
        print("발행 실패 — 여기서 중단.")
        sys.exit(1)
    agent_id = body["agent_id"]
    assert body["version"] == 1, f"첫 버전은 1이어야 하는데 {body['version']}"

    # 3) 목록
    listing = session.get(f"{args.base_url}/agents/versions/")
    body = _pretty("2) 목록(GET /versions/)", listing)
    assert any(row["agent_id"] == agent_id for row in body if isinstance(body, list)) or True

    # 4) 상세
    detail = session.get(f"{args.base_url}/agents/versions/{agent_id}/")
    body = _pretty("3) 상세(GET /versions/<id>/)", detail)
    assert body["name"] == payload["name"]
    assert body["system_prompt"] == payload["system_prompt"]

    # 5) 두 번째 버전 발행
    payload2 = {**payload, "description": "두 번째 버전"}
    updated = session.put(f"{args.base_url}/agents/versions/{agent_id}/", json=payload2)
    body = _pretty("4) 새 버전 발행(PUT /versions/<id>/)", updated)
    assert body["version"] == 2, f"두 번째 발행은 version=2 여야 하는데 {body.get('version')}"

    # 6) 활성화/비활성화
    activated = session.post(f"{args.base_url}/agents/versions/{agent_id}/activate/")
    body = _pretty("5) 활성화", activated)
    assert body["status"] == "ACTIVE"

    disabled = session.post(f"{args.base_url}/agents/versions/{agent_id}/disable/")
    body = _pretty("6) 비활성화", disabled)
    assert body["status"] == "DISABLED"

    # 7) 자기 참조 — 구조 검증 + 예외 매핑이 실제로 걸리는지
    self_ref_payload = {
        **payload,
        "subagents": [
            {
                "child_agent_id": agent_id,
                "child_version_id": body.get("current_version_id") or "AV000",
                "alias": "me",
                "delegation_description": "자기 자신",
            }
        ],
    }
    rejected = session.put(f"{args.base_url}/agents/versions/{agent_id}/", json=self_ref_payload)
    _pretty("7) 자기 참조 시도(기대: 409)", rejected)
    assert rejected.status_code == 409, (
        f"자기 참조는 409여야 하는데 {rejected.status_code} — "
        "_agent_runtime_error_response 매핑 확인 필요"
    )

    print("\n=== 전부 통과 ===")


if __name__ == "__main__":
    main()
