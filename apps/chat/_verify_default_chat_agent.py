"""기본 챗 에이전트(AG002 등)로 실제 세션을 만들고 메시지 한 번 보내보는 1회용 검증 스크립트.

로컬 Docker DB(localhost:5432)를 향한 `manage.py runserver`가 떠 있어야 한다.
이메일·비밀번호는 여기 안 남기고 실행할 때 직접 입력한다 — Claude(나)한테도 안 보인다.

사용법 (venv 활성화한 cmd, 로컬 서버가 http://localhost:8000 에 떠 있는 상태에서):
    python apps/chat/_verify_default_chat_agent.py AG002
"""

import getpass
import json
import sys

import requests

BASE = "http://localhost:8000/api"


def main() -> int:
    if len(sys.argv) != 2:
        print("사용법: python apps/chat/_verify_default_chat_agent.py <agent_id>")
        return 1
    agent_id = sys.argv[1]

    email = input("이메일: ").strip()
    password = getpass.getpass("비밀번호: ")

    login = requests.post(f"{BASE}/auth/login/", json={"email": email, "password": password})
    if login.status_code != 200:
        print("로그인 실패:", login.status_code, login.text)
        return 1
    token = login.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    account = login.json().get("account", {})
    print("로그인 성공. account_id =", account.get("account_id"))

    # 진단용 — 서버가 실제로 어느 DB를 보고 있는지 확인한다. 여기 목록에
    # agent_id 가 안 뜨면 서버가 로컬 DB가 아니라 다른 DB(.env의 RDS 등)를
    # 보고 있다는 뜻이다.
    versions = requests.get(f"{BASE}/agents/versions/", headers=headers)
    print("GET /agents/versions/ ->", versions.status_code)
    if versions.status_code == 200:
        for row in versions.json():
            print("  -", row.get("agent_id"), row.get("name"), row.get("status"))

    session = requests.post(
        f"{BASE}/chat/sessions/",
        json={"agent_id": agent_id, "proj_id": None, "title": "기본 챗 에이전트 검증"},
        headers=headers,
    )
    if session.status_code not in (200, 201):
        print("세션 생성 실패:", session.status_code, session.text)
        return 1
    session_id = session.json()["session_id"]
    print("세션 생성 성공:", session_id)

    print("메시지 전송 중... (스트리밍 응답)")
    with requests.post(
        f"{BASE}/chat/sessions/{session_id}/messages/",
        json={"content": "안녕, 지금 잘 들리니? 짧게 대답해줘."},
        headers=headers,
        stream=True,
    ) as resp:
        if resp.status_code != 200:
            print("메시지 전송 실패:", resp.status_code, resp.text)
            return 1
        for line in resp.iter_lines():
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                print("RAW:", line)
                continue
            print(event.get("type"), "-", {k: v for k, v in event.items() if k != "type"})

    print("\n완료 — 위에 result/error 이벤트가 찍혔으면 그게 결과다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
