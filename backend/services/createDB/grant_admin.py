"""운영자 콘솔 관리자 권한 부여·회수 스크립트.

`vec_idx_setup.py`와 같은 방식으로 컨테이너 안이 아니라 호스트 Python에서
직접 실행한다. `user_account.is_admin`을 API가 아니라 이 스크립트로만 켜고
끄는 이유는, 관리자 승격 경로를 API 표면에 아예 두지 않기 위해서다(자기 자신을
포함해 그 누구도 요청 한 번으로 관리자가 될 수 없다).

실행 전: 대상 이메일이 이미 일반 회원가입으로 `user_account`에 존재해야 한다.

사용법:
    DATABASE_URL="postgres://project_copilot:project_copilot@localhost:5432/project_copilot" \\
      python backend/services/createDB/grant_admin.py teamlead@halil.ai
    python backend/services/createDB/grant_admin.py teamlead@halil.ai --revoke
"""

import argparse
import os
import sys

import psycopg

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgres://project_copilot:project_copilot@localhost:5432/project_copilot",
)


def get_conn():
    return psycopg.connect(DATABASE_URL)


def set_admin(conn, *, email: str, is_admin: bool) -> dict | None:
    """`is_admin`을 갱신하고 갱신된 계정 정보를 돌려준다. 대상이 없으면 None."""

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE user_account
            SET is_admin = %s
            WHERE lower(email) = lower(%s)
            RETURNING account_id, email, display_name, account_status
            """,
            (is_admin, email),
        )
        row = cur.fetchone()
    conn.commit()
    if row is None:
        return None
    return {"account_id": row[0], "email": row[1], "display_name": row[2], "account_status": row[3]}


def main() -> int:
    parser = argparse.ArgumentParser(description="운영자 콘솔 관리자 권한 부여·회수")
    parser.add_argument("email", help="권한을 바꿀 계정의 가입 이메일")
    parser.add_argument("--revoke", action="store_true", help="관리자 권한을 회수한다(기본은 부여)")
    args = parser.parse_args()

    conn = get_conn()
    try:
        account = set_admin(conn, email=args.email, is_admin=not args.revoke)
    finally:
        conn.close()

    if account is None:
        print(f"가입되지 않은 이메일입니다: {args.email}. 먼저 일반 회원가입을 진행해 주세요.")
        return 1

    action = "회수" if args.revoke else "부여"
    print(
        f"관리자 권한을 {action}했습니다: {account['email']} "
        f"(account_id={account['account_id']}, display_name={account['display_name']}, "
        f"account_status={account['account_status']})"
    )
    if not args.revoke and account["account_status"] != "ACTIVE":
        print(f"주의: 계정 상태가 {account['account_status']}라서 이 상태로는 관리자 로그인도 막혀 있습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
