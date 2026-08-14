"""운영자 계정 시드.

`grant_admin.py`·`seed_agents.py`와 같이 API가 아니라 스크립트로만 실행한다.
이유도 같다 — **운영자 승격 경로를 API 표면에 두지 않는다**(`grant_admin.py`
주석 참고). 이 스크립트는 그 결정을 지키면서 `reset_demo.sql` 직후의 불편만
없앤다.

`reset_demo.sql`은 `user_account`를 비우므로 `is_admin = true`인 계정이 사라져
`/ops/login`에 들어갈 방법이 없어진다. 원래는 「회원가입 → grant_admin.py」
두 단계를 밟아야 하는데, 시연 초기화 때마다 반복되고 잊기도 쉽다. 이 스크립트는
**계정 생성과 승격을 한 번에** 한다.

⚠ 비밀번호를 소스에 두지 않는다. `.env`의 `OPS_ADMIN_PASSWORD`를 읽고, 없으면
그냥 실패한다 — 기본값을 두면 그 값이 공개 서버의 실제 비밀번호가 된다.
`halil-ai.site`는 인터넷에 열려 있고 배포 몇 분 만에 스캐너가 훑고 갔다.

멱등하다. 이미 있는 이메일이면 비밀번호와 `is_admin`을 맞추기만 한다.

사용법:
    # .env 에 OPS_ADMIN_EMAIL, OPS_ADMIN_PASSWORD 를 채운 뒤
    python backend/services/createDB/seed_ops_admin.py

    # 값을 그때그때 주고 싶으면
    OPS_ADMIN_EMAIL=ops@example.com OPS_ADMIN_PASSWORD='...' \\
      python backend/services/createDB/seed_ops_admin.py
"""

import os
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

# `config`(Django 설정)를 import 하려면 저장소 루트가 sys.path 에 있어야 한다.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import django  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from django.contrib.auth.hashers import make_password  # noqa: E402

from backend.db.codes import next_short_code  # noqa: E402

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgres://project_copilot:project_copilot@localhost:5432/project_copilot",
)


def main() -> int:
    email = os.environ.get("OPS_ADMIN_EMAIL", "").strip()
    password = os.environ.get("OPS_ADMIN_PASSWORD", "")

    if not email or not password:
        print(
            "OPS_ADMIN_EMAIL 과 OPS_ADMIN_PASSWORD 가 모두 필요하다.\n"
            "`.env` 에 넣거나 명령 앞에 붙여서 준다. 기본값은 두지 않는다.",
            file=sys.stderr,
        )
        return 2

    display_name = os.environ.get("OPS_ADMIN_DISPLAY_NAME", "운영자").strip() or "운영자"
    password_hash = make_password(password)

    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT account_id, is_admin FROM user_account WHERE lower(email) = lower(%s)",
                (email,),
            )
            existing = cur.fetchone()

            if existing is None:
                account_id = next_short_code(
                    cur, table="user_account", column="account_id", prefix="UA"
                )
                cur.execute(
                    """
                    INSERT INTO user_account
                        (account_id, email, password_hash, display_name, is_admin)
                    VALUES (%s, %s, %s, %s, true)
                    """,
                    (account_id, email, password_hash, display_name),
                )
                action = "만들었다"
            else:
                account_id = existing["account_id"]
                cur.execute(
                    """
                    UPDATE user_account
                    SET password_hash = %s, is_admin = true
                    WHERE account_id = %s
                    """,
                    (password_hash, account_id),
                )
                action = "이미 있어서 비밀번호와 권한만 맞췄다"
        conn.commit()

    print(f"운영자 계정 {account_id} ({email}) — {action}.")
    print("이 계정은 팀에 속하지 않는다. /ops/login 전용이다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
