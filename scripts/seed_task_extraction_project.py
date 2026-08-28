"""업무 추출 에이전트 실측용 프로젝트 + 기준 문서를 만든다.

`web` 컨테이너에서 실행한다:

    docker exec skn29-final-2team-web-1 python scripts/seed_task_extraction_project.py [account_email]

- 프로젝트 하나(ACTIVE, Asia/Seoul)를 만든다.
- 업무가 뚜렷하게 적힌 한국어 Markdown 을 팀 문서로 올리고 그 프로젝트의
  **기준 문서(`doc_role='PRIMARY'`)** 로 지정한다.
- 색인은 안 한다 — `task_extraction` 이 기준 문서가 아직 검색 불가면 그 자리에서
  `promote_to_searchable()` 로 끌어올린다(RunPod 필요).
- 같은 이름의 기존 픽스처(프로젝트·문서)는 지우고 다시 만든다.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from backend.db.connection import database_connection  # noqa: E402
from backend.db.repositories import DocumentRepository, ProjectRepository  # noqa: E402
from backend.db.codes import next_short_code  # noqa: E402
from backend.services import storage  # noqa: E402

PROJECT_NAME = "테스트 프로젝트 (업무추출)"
DOC_NAME = "사내_지식관리_시스템_구축_제안요청서.md"
_MD = "text/markdown"

RFP_MARKDOWN = """# 사내 지식관리(PKM) 시스템 구축 제안요청서

## 1. 사업 개요

본 사업은 흩어진 사내 문서와 회의록을 한곳에서 검색하고, 프로젝트별로
필요한 지식을 정리해 주는 사내 지식관리 시스템을 구축하는 것을 목적으로 한다.
개발 기간은 2026년 9월 1일부터 2026년 11월 30일까지 3개월로 한다.

## 2. 과업 범위

### 2.1 문서 수집·색인
- Google Drive 와 사내 위키의 문서를 주기적으로 수집한다.
- 수집한 문서를 문단 단위로 쪼개 임베딩하고 벡터 검색 색인을 만든다.
- 담당 역할: 백엔드 개발자. 예상 공수 80시간. 2026년 9월 30일까지 완료한다.

### 2.2 의미 기반 검색 API
- 자연어 질의를 받아 관련 문단과 출처 문서를 함께 돌려주는 REST API 를 만든다.
- 검색 결과에는 반드시 원문 근거(문서명, 문단 위치)를 포함한다.
- 담당 역할: 백엔드 개발자. 예상 공수 60시간. 2026년 10월 15일까지 완료한다.
- 선행 조건: 2.1 문서 색인이 완료되어 있어야 한다.

### 2.3 프로젝트별 지식 정리 화면
- 프로젝트를 고르면 그 프로젝트에 관련된 문서와 핵심 지식을 카드로 보여준다.
- 담당 역할: 프론트엔드 개발자. 예상 공수 50시간. 2026년 10월 31일까지 완료한다.

### 2.4 업무 추출 기능
- 프로젝트 기준 문서에서 수행해야 할 업무 후보를 자동으로 뽑아 목록으로 만든다.
- 각 업무에는 담당 역할, 예상 공수, 마감일, 원문 근거를 붙인다.
- 담당 역할: 백엔드 개발자. 예상 공수 40시간. 2026년 11월 15일까지 완료한다.
- 선행 조건: 2.2 검색 API 가 동작해야 한다.

## 3. 완료 기준

- 문서 1만 건 색인 기준 평균 검색 응답 시간 2초 이내.
- 검색 결과 상위 5건의 근거 정확도(사람 평가) 80퍼센트 이상.
- 업무 추출 결과에 근거 없는 업무가 한 건도 없어야 한다.

## 4. 산출물

- 시스템 아키텍처 설계서
- API 명세서
- 사용자 매뉴얼
- 최종 소스 코드와 배포 스크립트

## 5. 위험 요소

- 임베딩 모델 호스팅 비용이 예상보다 클 수 있다.
- 사내 위키 접근 권한 협의가 지연되면 2.1 착수가 늦어진다.
"""


def _resolve_account(email: str | None) -> str:
    with database_connection() as connection, connection.cursor() as cursor:
        if email:
            cursor.execute(
                "SELECT account_id FROM user_account WHERE lower(email) = lower(%s)", (email,)
            )
        else:
            cursor.execute(
                "SELECT account_id FROM user_account WHERE account_status = 'ACTIVE' "
                "ORDER BY account_id LIMIT 1"
            )
        row = cursor.fetchone()
    if row is None:
        raise SystemExit(f"계정을 찾지 못했습니다: {email or '(ACTIVE 없음)'}")
    return row["account_id"]


def _purge(account_id: str) -> None:
    """같은 이름의 이전 픽스처를 지운다(멱등 재실행)."""
    with database_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT team_id FROM user_account WHERE account_id = %s", (account_id,))
        team_id = cursor.fetchone()["team_id"]

        cursor.execute(
            "SELECT proj_id FROM proj WHERE team_id = %s AND name = %s", (team_id, PROJECT_NAME)
        )
        for row in list(cursor.fetchall()):
            cursor.execute(
                "SELECT doc_id, storage_key FROM doc WHERE proj_id = %s", (row["proj_id"],)
            )
            for doc in list(cursor.fetchall()):
                if doc["storage_key"]:
                    try:
                        storage.remove(doc["storage_key"])
                    except Exception:  # noqa: BLE001
                        pass
                cursor.execute("DELETE FROM doc WHERE doc_id = %s", (doc["doc_id"],))
            cursor.execute("DELETE FROM proj_member WHERE proj_id = %s", (row["proj_id"],))
            cursor.execute("DELETE FROM proj WHERE proj_id = %s", (row["proj_id"],))


def main() -> int:
    email = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SEED_ACCOUNT_EMAIL")
    account_id = _resolve_account(email)
    _purge(account_id)

    project = ProjectRepository.create(
        name=PROJECT_NAME,
        status="ACTIVE",
        tz="Asia/Seoul",
        owner_account_id=account_id,
        description="업무 추출 에이전트 실측용. 기준 문서에서 업무를 뽑는다.",
    )
    proj_id = project["proj_id"]
    team_id = project["team_id"]

    data = RFP_MARKDOWN.encode("utf-8")
    with database_connection() as connection, connection.cursor() as cursor:
        doc_id = next_short_code(cursor, table="doc", column="doc_id", prefix="DC")
        cursor.execute(
            """
            INSERT INTO doc
                (doc_id, team_id, proj_id, source_type, file_name, mime_type, doc_role)
            VALUES (%s, %s, %s, 'UPLOAD', %s, %s, 'PRIMARY')
            """,
            (doc_id, team_id, proj_id, DOC_NAME, _MD),
        )

    key = storage.build_key(team_id=team_id, doc_id=doc_id, mime_type=_MD)
    content_hash = storage.save(key, data)
    DocumentRepository.mark_stored(
        doc_id=doc_id,
        storage_key=key,
        content_hash=content_hash,
        revision=content_hash.removeprefix("sha256:")[:16],
    )

    print(
        f"project={proj_id} ({PROJECT_NAME})  primary_doc={doc_id} ({DOC_NAME})  "
        f"account={account_id} team={team_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
