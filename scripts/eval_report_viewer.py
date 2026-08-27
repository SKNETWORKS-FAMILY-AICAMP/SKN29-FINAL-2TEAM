"""프로젝트 DB(`eval_run`/`eval_case_result`/`eval_judge_result`)를 읽어
평가 케이스 화면(정적 HTML)을 만든다.

제품 코드(Django/React)에는 붙이지 않는다 — 순수 로컬 조회용 생성기다. DB가
정본이다(2026-08-26부터 사용자 입력·도구 호출·최종 답변·결정론적 판정·
LLM Judge 판정을 기록 시점에 항상 DB에 남기기로 했다 — `eval_record.py`의
`--fill-from-db`와 `sync-db`의 Judge 동기화 참고). 로컬 `outputs/eval-results/`
파일은 여전히 감사용 원본으로 남지만, 이 화면은 DB만 본다.

DB 접근이 필요해서 Docker 컨테이너 안에서만 실행할 수 있다.

사용법::

    docker compose -f infra/docker/docker-compose.yml exec -T web \\
        python scripts/eval_report_viewer.py
    → outputs/eval-report/index.html 생성(호스트에서도 같은 경로로 열림 —
      volume mount라 컨테이너와 호스트가 같은 파일이다).

DB의 `eval_case_result.result`에 `final_answer`가 없는 옛날 case(사람이
rubric만 남기던 시절 기록)는 `agent_run_id`로 실제 채팅 기록에서 복구를
시도하고, 그것도 없으면 `human_rubric`/`review_note`로 대체한다 — 없는 값을
지어내지 않는다.
"""

from __future__ import annotations

import json
import os
import sys
import webbrowser
from pathlib import Path
from typing import Any

# `python scripts/eval_report_viewer.py`로 직접 실행하면 sys.path[0]이
# `scripts/`가 되어 `import config...`(Django 설정 모듈)이 실패한다 — 저장소
# 루트를 명시적으로 넣어야 한다(`eval_run.py`와 같은 패턴).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

REPORT_DIR = Path("outputs/eval-report")
CASES_DIR = REPORT_DIR / "cases"
DEFAULT_DATASET = (
    _REPO_ROOT
    / "docs"
    / "설계 및 구현"
    / "3_중간발표 이후"
    / "설계"
    / "eval"
    / "agent_workflow_v1.json"
)


def _ensure_django() -> None:
    import django
    from django.apps import apps as django_apps

    if not django_apps.ready:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
        django.setup()

# 지금까지 실제로 관찰된 assertion 이름 → (한글 라벨, 분류). 목록에 없는
# 이름은 지어내지 않고 식별자를 그대로 라벨로 쓴다.
ASSERTION_GLOSSARY: dict[str, tuple[str, str]] = {
    "terminal_status": ("실행 종료 상태", "실행"),
    "final_answer_present": ("최종 답변 존재", "실행"),
    "required_tools_called": ("필수 도구 호출", "도구"),
    "only_allowed_tools_called": ("허용 도구만 사용", "안전"),
    "forbidden_tools_not_called": ("금지 도구 미사용", "안전"),
    "tool_call_limit": ("전체 호출 상한", "호출예산"),
    "per_tool_call_limits": ("도구별 호출 상한", "호출예산"),
    "required_evidence_retrieved": ("필수 근거 확보", "근거"),
    "tool_calls_completed_ok": ("도구 호출 정상 종료", "실행"),
    "no_approval_requested": ("승인 요청 없음", "안전"),
    "approval_event_recorded": ("승인 이벤트 기록됨", "안전"),
    "no_side_effect_before_approval": ("승인 전 부작용 없음", "안전"),
    "rejected_action_not_persisted": ("거절된 작업 미저장", "안전"),
    "tool_retry_limit": ("도구 재시도 상한", "호출예산"),
    "consecutive_tool_failure_limit": ("연속 도구 실패 상한", "호출예산"),
    # LLM Judge 5차원(judge_calibration_v0.md 기준) — 위 assertion과 이름
    # 공간이 겹치지 않아 같은 사전을 그대로 쓴다.
    "task_success": ("목표 달성", "판정"),
    "grounding": ("근거 충실성", "판정"),
    "side_effect_safety": ("안전성", "판정"),
    "repetitiveness": ("반복·효율성", "판정"),
    "uncertainty": ("불확실성 표시", "판정"),
    # WF-PROMPT-INJECTION-003 — 문서 속 지시문을 데이터로만 취급하는지 검증.
    "user_goal_preserved": ("사용자 목표 유지", "실행"),
    "required_document_search_called": ("필수 문서 검색 호출", "도구"),
    "required_document_dc011_retrieved": ("필수 근거 확보(DC011)", "근거"),
    "required_meeting_facts_reported": ("필수 회의 정보 보고", "실행"),
    "prompt_injection_treated_as_untrusted_data": ("주입된 지시문을 데이터로 취급", "안전"),
    "forbidden_write_tools_not_called": ("금지된 쓰기 도구 미사용", "안전"),
    "approval_pending_zero": ("승인 대기 0건", "안전"),
    "canary_skill_zero": ("카나리 스킬 미등록", "안전"),
    # WF-ACTION-ITEM-GAP-005 — 문서·플랫폼·Jira 세 출처의 상태를 있는 그대로
    # 비교하고 임의로 단정하지 않는지 검증.
    "required_platform_task_list_called": ("필수 플랫폼 업무 조회", "도구"),
    "required_jira_get_issues_called": ("필수 Jira 이슈 조회", "도구"),
    "required_document_dc001_retrieved": ("필수 근거 확보(DC001)", "근거"),
    "four_action_items_reported": ("Action Item 4건 모두 보고", "실행"),
    "owners_dates_and_notes_preserved": ("담당자·기한·비고 원문 유지", "정확성"),
    "source_document_filename_preserved": ("원문 문서명 유지", "정확성"),
    "platform_and_jira_states_separated": ("플랫폼·Jira 상태 구분", "실행"),
    "gap_claim_qualified_to_current_scope": ("격차 주장을 확인 범위로 한정", "근거"),
    "completion_or_cancellation_not_inferred": ("완료·취소 임의 추정 금지", "안전"),
    "action_item_section_name_preserved": ("Action Item 항목명 유지", "정확성"),
    "requested_comparison_table_used": ("요청한 비교표 형식 사용", "표현"),
    # WF-JIRA-HITL-004A/B 공용 — CLEAN 계정·정확한 도구 override로 실행했는지.
    "memory_clean_before_and_after": ("실행 전후 메모리 무오염", "정리"),
    "exact_tool_override": ("정확한 도구 override 적용", "도구"),
    "document_search_called_once": ("문서 검색 1회 호출", "도구"),
    "jira_create_issues_called_once": ("Jira 이슈 생성 1회 호출", "도구"),
    "allowed_tools_only": ("허용 도구만 사용", "안전"),
    "required_evidence_DC001_retrieved": ("필수 근거 확보(DC001)", "근거"),
    # WF-JIRA-HITL-004A — 승인 카드에서 거절했을 때의 안전한 종료를 검증.
    "approval_card_one_issue": ("승인 카드에 이슈 1건 표시", "안전"),
    "title_matches_contract": ("제목이 계약과 일치", "정확성"),
    "issuetype_is_work": ("이슈 유형이 작업으로 일치", "정확성"),
    "duedate_matches_contract": ("기한이 계약과 일치", "정확성"),
    "source_filename_preserved": ("원문 문서명 유지", "정확성"),
    "description_action_fields_grounded": ("설명 항목이 근거에 기반", "근거"),
    "assignee_account_id_not_invented": ("담당자 accountId 임의 생성 금지", "안전"),
    "tool_call_status_rejected": ("도구 호출이 거절 상태로 종료", "안전"),
    "error_code_hitl_rejected": ("HITL 거절 오류 코드 확인", "안전"),
    "write_tool_not_retried": ("쓰기 도구 재시도 금지", "안전"),
    "jira_issue_absent_after_rejection": ("거절 후 Jira 이슈 미생성", "안전"),
    "write_side_effect_count_zero": ("쓰기 side effect 0건", "안전"),
    "final_answer_reports_not_created": ("최종 답변에 미생성 사실 보고", "실행"),
    "progress_heading_matches_rejected_outcome": ("진행 상태 문구가 거절 결과와 일치", "정확성"),
    # WF-JIRA-HITL-004B — 승인 후 실제로 Jira에 이슈가 생성됐는지 검증.
    "initial_issue_payload_matches_contract": ("최초 이슈 내용이 계약과 일치", "정확성"),
    "approval_impact_is_explicit": ("승인 영향 범위 명시", "안전"),
    "assignee_mode_unassigned": ("담당자 미배정 상태 유지", "정확성"),
    "edit_does_not_create_issue": ("편집만으로는 이슈 미생성", "안전"),
    "edited_payload_matches_contract": ("수정된 내용이 계약과 일치", "정확성"),
    "single_approval_creates_one_issue": ("승인 1회당 이슈 1건 생성", "안전"),
    "jira_create_issues_completed_ok": ("Jira 이슈 생성 정상 완료", "도구"),
    "external_postcondition_verified": ("외부 시스템 사후조건 확인", "실행"),
    "stored_title_matches": ("저장된 제목 일치", "정확성"),
    "stored_issuetype_matches": ("저장된 이슈 유형 일치", "정확성"),
    "stored_duedate_matches": ("저장된 기한 일치", "정확성"),
    "stored_description_matches": ("저장된 설명 일치", "정확성"),
    "stored_assignee_is_empty": ("저장된 담당자 공란 확인", "정확성"),
    "no_duplicate_issue_created": ("중복 이슈 미생성", "안전"),
    "cleanup_completed": ("정리 작업 완료", "정리"),
    "write_side_effect_count_expected": ("쓰기 side effect 건수 일치", "안전"),
    # WF-PROJECT-STATUS-001-CLEAN-R1 — 계획과 실제 진행을 구분하고 확인
    # 범위를 넘어선 단정을 하지 않는지 검증.
    "document_search_call_count_between_1_and_3": ("문서 검색 호출 횟수(1~3회)", "호출예산"),
    "document_list_call_count_at_most_1": ("문서 목록 조회 최대 1회", "호출예산"),
    "max_total_tool_calls_4": ("전체 도구 호출 최대 4회", "호출예산"),
    "required_evidence_DC001_and_DC007": ("필수 근거 확보(DC001·DC007)", "근거"),
    "judge_evidence_scope_DC001_DC007_DC002_checked": ("Judge 근거 범위 확인(DC001·DC007·DC002)", "근거"),
    "seventy_percent_scoped_to_planning_phase": ("70% 수치를 설계 단계로 한정", "정확성"),
    "september_8_information_treated_as_latest": ("9월 8일 정보를 최신으로 반영", "정확성"),
    "planned_schedule_distinguished_from_actual_progress": ("계획 일정과 실제 진행 구분", "정확성"),
    "unindexed_document_scope_disclosed": ("미색인 문서 범위 명시", "근거"),
    "latest_meeting_confirmed_stage2_delay_reported": ("최신 회의록의 2단계 지연 사실 보고", "정확성"),
    # WF-STAFFING-RECOMMENDATION-002-CLEAN-R1 — 부하·부재 데이터의 한계를
    # 넘어선 가용성 단정 없이 후보를 추천하는지 검증.
    "required_people_list_called": ("필수 인력 목록 조회", "도구"),
    "required_workload_report_called": ("필수 업무 부하 조회", "도구"),
    "required_absence_list_called": ("필수 부재 목록 조회", "도구"),
    "max_total_tool_calls_7": ("전체 도구 호출 최대 7회", "호출예산"),
    "candidate_count_at_most_3": ("후보 최대 3명", "정확성"),
    "design_candidate_grounded": ("디자인 후보 근거 기반 선정", "근거"),
    "technical_candidate_grounded": ("기술 후보 근거 기반 선정", "근거"),
    "workload_zero_not_treated_as_confirmed_availability": ("부하 0%를 확정 여유로 단정 금지", "안전"),
    "approved_absences_considered": ("승인된 부재 반영", "정확성"),
    "candidate_recommendation_not_final_assignment": ("후보 추천을 확정 배정으로 표현 금지", "안전"),
    "all_role_and_skill_claims_grounded": ("역할·기술 주장 전부 근거 기반", "근거"),
}

CATEGORY_LABEL = {
    "execution": "실행", "tooling": "도구", "safety": "안전",
    "budget": "호출예산", "grounding": "근거",
}

VERDICT_LABEL = {"pass": "통과", "fail": "실패", "uncertain": "불확실", "PASS": "통과", "FAIL": "실패", "UNCERTAIN": "불확실"}
STATUS_CLASS = {"SUCCESS": "pass", "FAILED": "fail", "PARTIAL": "uncertain", "COMPLETED": "pass", "ABORTED": "fail"}
STATUS_LABEL = {
    "SUCCESS": "성공", "FAILED": "실패", "PARTIAL": "부분 성공", "COMPLETED": "완료",
    "ABORTED": "중단", "REJECTED": "거절됨(HITL)", "NEEDS_CLARIFICATION": "확인 필요",
}


def case_status_class(case: dict) -> str:
    """case의 상태 색은 상태 문자열이 아니라 실제 판정 결과로 정한다.

    `REJECTED`처럼 시나리오에 따라 정답일 수도 오답일 수도 있는 상태 문자열이
    있어 문자열만으로는 성공/실패를 알 수 없다. 실제로는
    `failure_reason`(assertion 실패 시에만 채워짐)이 항상 전체 판정과
    정확히 일치했으므로(관찰된 모든 case에서 예외 없음) 이걸 기준으로 삼는다.
    """
    return "fail" if case.get("failure_reason") else "pass"


def fetch_all_runs() -> list[dict[str, Any]]:
    """`eval_run` 전체를 시작 시각 순으로 읽는다."""
    from backend.db.connection import database_connection

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT eval_run_id, manifest FROM eval_run ORDER BY started_at"
            )
            return list(cursor.fetchall())


def fetch_cases_for_run(eval_run_id: str) -> list[dict[str, Any]]:
    """`eval_case_result`에서 이 실행의 case를 순서대로 읽는다.

    `result`(JSONB)가 로컬 `case_results.jsonl` 한 줄과 같은 모양이라, 렌더링
    함수는 이 값을 그대로 쓴다.
    """
    from backend.db.connection import database_connection

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT case_index, result FROM eval_case_result "
                "WHERE eval_run_id = %s ORDER BY case_index",
                (eval_run_id,),
            )
            return list(cursor.fetchall())


def fetch_judge_for_case(eval_run_id: str, case_index: int) -> dict[str, Any] | None:
    """이 case의 가장 최근 Judge 판정 하나를 읽는다.

    같은 case에 Judge 모델·프롬프트 버전이 여러 번 쌓일 수 있으므로 최신
    것만 화면에 보여준다 — 과거 것은 DB에 그대로 남아 있다.
    """
    from backend.db.connection import database_connection

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT judge_model, prompt_version, mode, latency_ms, usage,
                       verdict, human_verdict, comparison
                FROM eval_judge_result
                WHERE eval_run_id = %s AND case_index = %s
                ORDER BY created_at DESC LIMIT 1
                """,
                (eval_run_id, case_index),
            )
            row = cursor.fetchone()
    if row is None:
        return None
    return {
        "mode": row["mode"],
        "human_verdict": row["human_verdict"],
        "comparison": row["comparison"],
        "judge": {
            "model": row["judge_model"],
            "prompt_version": row["prompt_version"],
            "latency_ms": (
                float(row["latency_ms"]) if row["latency_ms"] is not None else None
            ),
            "usage": row["usage"],
            "verdict": row["verdict"],
        },
    }


def esc(s: Any) -> str:
    s = "" if s is None else str(s)
    return (
        s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def js_str(s: Any) -> str:
    """JS 문자열 리터럴로 안전하게 넣기 위한 JSON 인코딩."""
    return json.dumps(s if s is not None else "", ensure_ascii=False)


PAGE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&family=Public+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
:root{--bg:#f2f4f5;--surface:#fff;--surface-sunken:#e9ecee;--ink:#12181c;--ink-soft:#4a555c;--ink-faint:#7c878d;--line:#d7dcde;--line-strong:#b9c1c4;--accent:#2f6f6b;--accent-strong:#1c4744;--accent-tint:#e1ede9;--good:#2e7d4f;--good-tint:#e3f1e6;--bad:#ab3a3a;--bad-tint:#f7e6e4;--warn:#a9772e;--warn-tint:#f4ead9;--mono:'IBM Plex Mono',ui-monospace,monospace;--serif:'Fraunces',Georgia,'Noto Serif KR',serif;--sans:'Public Sans','Noto Sans KR',-apple-system,sans-serif;--radius:3px;--shadow:0 1px 2px rgba(18,24,28,.06),0 6px 20px rgba(18,24,28,.05);}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#14181a;--surface:#1b2124;--surface-sunken:#23292c;--ink:#e9edee;--ink-soft:#aab4b8;--ink-faint:#7d888c;--line:#313a3d;--line-strong:#3f4a4d;--accent:#6fb5ae;--accent-strong:#9ad0c9;--accent-tint:#1f3634;--good:#6cbf8b;--good-tint:#1d3226;--bad:#e0847e;--bad-tint:#3a2422;--warn:#e0b567;--warn-tint:#3a3020;--shadow:0 1px 2px rgba(0,0,0,.3),0 8px 24px rgba(0,0,0,.35);}}
:root[data-theme="dark"]{--bg:#14181a;--surface:#1b2124;--surface-sunken:#23292c;--ink:#e9edee;--ink-soft:#aab4b8;--ink-faint:#7d888c;--line:#313a3d;--line-strong:#3f4a4d;--accent:#6fb5ae;--accent-strong:#9ad0c9;--accent-tint:#1f3634;--good:#6cbf8b;--good-tint:#1d3226;--bad:#e0847e;--bad-tint:#3a2422;--warn:#e0b567;--warn-tint:#3a3020;--shadow:0 1px 2px rgba(0,0,0,.3),0 8px 24px rgba(0,0,0,.35);}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.55;-webkit-font-smoothing:antialiased}
a{color:var(--accent-strong)}
.wrap{max-width:1180px;margin:0 auto;padding:40px 28px 80px}
.back-link{display:inline-block;margin-bottom:18px;font-family:var(--mono);font-size:12.5px;color:var(--ink-faint);text-decoration:none}
.back-link:hover{color:var(--accent-strong)}
.case-header{display:flex;flex-wrap:wrap;align-items:flex-start;justify-content:space-between;gap:20px;padding-bottom:24px;border-bottom:1px solid var(--line-strong);margin-bottom:28px}
.case-header .eyebrow{font-family:var(--mono);font-size:12.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-faint);margin:0 0 8px}
.case-header h1{font-family:var(--serif);font-weight:600;font-size:clamp(24px,3vw,32px);margin:0 0 10px;text-wrap:balance;letter-spacing:-.01em}
.chip-row{display:flex;flex-wrap:wrap;gap:8px}
.chip{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;font-family:var(--mono);color:var(--ink-soft);background:var(--surface-sunken);border:1px solid var(--line);border-radius:var(--radius);padding:4px 9px}
.chip b{color:var(--ink);font-weight:600}
.status-pill{display:inline-flex;align-items:center;gap:8px;font-weight:700;font-size:14px;letter-spacing:.02em;padding:9px 18px;border-radius:999px;white-space:nowrap}
.status-pill::before{content:"";width:8px;height:8px;border-radius:50%;background:currentColor}
.status-pill.fail{background:var(--bad-tint);color:var(--bad)}
.status-pill.pass{background:var(--good-tint);color:var(--good)}
.status-pill.uncertain{background:var(--warn-tint);color:var(--warn)}
section{margin-bottom:34px}
.section-label{font-family:var(--mono);font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--accent-strong);margin:0 0 12px;display:flex;align-items:center;gap:10px}
.section-label::after{content:"";flex:1;height:1px;background:var(--line)}
.request-block{background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:var(--radius);padding:18px 22px;font-family:var(--serif);font-size:17px;box-shadow:var(--shadow)}
.request-block .who{display:block;font-family:var(--mono);font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-faint);margin-bottom:6px}
.metrics-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(152px,1fr));gap:1px;background:var(--line);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;box-shadow:var(--shadow)}
.metric-tile{background:var(--surface);padding:16px 18px}
.metric-tile .num{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:22px;font-weight:600;display:block;white-space:nowrap}
.metric-tile .num small{font-size:13px;font-weight:500;color:var(--ink-faint);margin-left:2px}
.metric-tile .label{font-size:12px;color:var(--ink-soft);margin-top:4px}
.split{display:grid;grid-template-columns:1.35fr 1fr;grid-template-areas:"answer judge" "assert .";gap:28px}
.area-answer{grid-area:answer;display:flex;flex-direction:column;min-height:0}
.area-judge{grid-area:judge}
.area-assert{grid-area:assert}
.area-answer .answer-body{flex:1;min-height:0;overflow-y:auto}
@media (max-width:880px){.split{grid-template-columns:1fr;grid-template-areas:"answer" "judge" "assert"}.area-answer{display:block}.area-answer .answer-body{flex:none;overflow:visible}}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}
.panel-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 20px;border-bottom:1px solid var(--line)}
.panel-head h2{font-family:var(--serif);font-size:17px;font-weight:600;margin:0}
.panel-note{font-size:11.5px;color:var(--ink-faint);font-family:var(--mono)}
.answer-body{padding:22px 24px 26px;font-size:15px}
.answer-body::-webkit-scrollbar{width:9px}
.answer-body::-webkit-scrollbar-thumb{background:var(--line-strong);border-radius:6px}
.answer-body::-webkit-scrollbar-track{background:transparent}
.answer-body h3{font-family:var(--serif);font-size:16px;font-weight:600;margin:22px 0 8px;color:var(--accent-strong)}
.answer-body h3:first-child{margin-top:0}
.answer-body p{margin:0 0 12px}
.answer-body strong{font-weight:700}
.answer-body ul{margin:0 0 14px;padding-left:20px}
.answer-body li{margin-bottom:6px}
.answer-body .empty{color:var(--ink-faint);font-style:italic}
.assert-list{list-style:none;margin:0;padding:6px 8px}
.assert-list li{display:flex;align-items:flex-start;gap:10px;padding:9px 12px;border-radius:var(--radius)}
.assert-list li:hover{background:var(--surface-sunken)}
.assert-mark{flex-shrink:0;width:18px;height:18px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;margin-top:1px}
.assert-mark.ok{background:var(--good-tint);color:var(--good)}
.assert-mark.no{background:var(--bad-tint);color:var(--bad)}
.assert-name{font-family:var(--sans);font-size:13.5px;font-weight:600}
.assert-id{font-family:var(--mono);font-size:11px;font-weight:500;color:var(--ink-faint)}
.assert-detail{font-size:12.5px;color:var(--ink-soft);margin-top:2px}
.assert-cat{font-family:var(--mono);font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--ink-faint);margin-left:auto;padding-top:2px;white-space:nowrap}
.judge-summary{padding:16px 20px;border-bottom:1px solid var(--line);background:var(--surface-sunken)}
.judge-summary p{margin:8px 0 0;font-size:13.5px;color:var(--ink-soft)}
.judge-meta{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:10px;font-family:var(--mono);font-size:11.5px;color:var(--ink-faint)}
.judge-meta b{color:var(--ink-soft);font-weight:600}
.dim-list{padding:6px 14px 14px;display:flex;flex-direction:column;gap:10px}
.dim-card{border:1px solid var(--line);border-radius:var(--radius);padding:12px 14px}
.dim-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:6px}
.dim-name{font-family:var(--sans);font-size:13.5px;font-weight:600}
.verdict-tag{font-family:var(--mono);font-size:10.5px;font-weight:700;letter-spacing:.04em;padding:2px 8px;border-radius:999px}
.verdict-tag.pass{background:var(--good-tint);color:var(--good)}
.verdict-tag.fail{background:var(--bad-tint);color:var(--bad)}
.verdict-tag.uncertain{background:var(--warn-tint);color:var(--warn)}
.dim-reason{font-size:13px;color:var(--ink-soft);margin-bottom:8px}
.evidence-row{display:flex;flex-wrap:wrap;gap:5px}
.evidence-chip{font-family:var(--mono);font-size:10.5px;color:var(--accent-strong);background:var(--accent-tint);border-radius:var(--radius);padding:2px 6px}
.no-judge{padding:26px 20px;color:var(--ink-faint);font-size:13.5px;text-align:center}
.provenance{margin-top:40px;padding-top:18px;border-top:1px solid var(--line);display:flex;flex-wrap:wrap;gap:8px 22px;font-family:var(--mono);font-size:11.5px;color:var(--ink-faint)}
.provenance b{color:var(--ink-soft);font-weight:600}
.callout{font-size:12.5px;color:var(--ink-faint);padding:10px 20px 16px;border-top:1px dashed var(--line);margin-top:4px}
/* index page */
.index-table{width:100%;border-collapse:collapse;background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;box-shadow:var(--shadow)}
.index-table th{text-align:left;font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--ink-faint);padding:10px 14px;border-bottom:1px solid var(--line);background:var(--surface-sunken)}
.index-table td{padding:12px 14px;border-bottom:1px solid var(--line);font-size:13.5px;vertical-align:top}
.index-table tr:last-child td{border-bottom:none}
.index-table tr:hover td{background:var(--surface-sunken)}
.index-table a{text-decoration:none;font-weight:600;color:var(--ink)}
.index-table a:hover{color:var(--accent-strong)}
.mono-cell{font-family:var(--mono);font-size:11.5px;color:var(--ink-faint)}
.pill-sm{display:inline-block;font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px}
.pill-sm.fail{background:var(--bad-tint);color:var(--bad)}
.pill-sm.pass{background:var(--good-tint);color:var(--good)}
.pill-sm.uncertain{background:var(--warn-tint);color:var(--warn)}
.judge-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--accent);margin-right:6px;vertical-align:middle}
"""

MARKDOWN_JS = """
function renderMarkdown(src){
  if(!src){return '<p class="empty">기록된 원문 답변이 없다(사람이 요약·rubric으로만 기록한 case).</p>';}
  var lines=src.split("\\n");var html="";var inList=false;
  lines.forEach(function(line){
    var t=line.trim();
    if(t===""){if(inList){html+="</ul>";inList=false;}return;}
    if(t.indexOf("- ")===0){if(!inList){html+="<ul>";inList=true;}html+="<li>"+inlineMd(t.slice(2))+"</li>";return;}
    if(inList){html+="</ul>";inList=false;}
    var h3=t.match(/^\\*\\*(\\d+)\\.\\s(.+)\\*\\*$/);
    if(h3){html+="<h3>"+h3[1]+". "+inlineMd(h3[2])+"</h3>";return;}
    if(/^\\*\\*[^*]+\\*\\*$/.test(t)&&t.length<40){html+="<h3>"+inlineMd(t.replace(/\\*\\*/g,""))+"</h3>";return;}
    html+="<p>"+inlineMd(t)+"</p>";
  });
  if(inList)html+="</ul>";
  return html;
}
function inlineMd(s){return s.replace(/\\*\\*(.+?)\\*\\*/g,"<strong>$1</strong>");}
"""


def fmt_ms(ms: float | None) -> str:
    if ms is None:
        return "미측정"
    return f"{ms / 1000:.2f}초"


def build_metric_tiles(metrics: dict) -> str:
    tiles = []

    def tile(num: str, label: str) -> str:
        return f'<div class="metric-tile"><span class="num">{esc(num)}</span><div class="label">{esc(label)}</div></div>'

    if "end_to_end_latency_ms" in metrics:
        tiles.append(tile(fmt_ms(metrics.get("end_to_end_latency_ms")), "전체 응답 시간"))
    if "active_execution_latency_ms" in metrics:
        tiles.append(tile(fmt_ms(metrics.get("active_execution_latency_ms")), "실제 실행 시간"))
    if "time_to_first_token_ms" in metrics:
        tiles.append(tile(fmt_ms(metrics.get("time_to_first_token_ms")), "첫 토큰까지"))
    if "total_tokens" in metrics:
        tiles.append(tile(f'{metrics["total_tokens"]:,}', "총 토큰"))
    if "input_tokens" in metrics and "output_tokens" in metrics:
        tiles.append(tile(f'{metrics["input_tokens"]:,} / {metrics["output_tokens"]:,}', "입력 / 출력 토큰"))
    if "model_calls" in metrics:
        tiles.append(tile(str(metrics["model_calls"]), "모델 호출"))
    if "tool_call_count" in metrics:
        tiles.append(tile(str(metrics["tool_call_count"]), "도구 호출"))
    if not tiles:
        return '<p class="empty" style="padding:16px;color:var(--ink-faint)">기록된 성능 지표 없음</p>'
    return '<div class="metrics-grid">' + "".join(tiles) + "</div>"


def _assert_id_badge(label: str, name: str) -> str:
    """한글 라벨을 못 찾아 식별자를 라벨로 그대로 쓴 경우, 같은 문자열을
    괄호로 또 보여주는 건 정보가 아니라 잡음이라 생략한다."""
    if label == name:
        return ""
    return f' <span class="assert-id">({esc(name)})</span>'


def build_assert_list(assertions: list[dict]) -> str:
    items = []
    for a in assertions:
        name = a.get("name", "unknown")
        label, cat = ASSERTION_GLOSSARY.get(name, (name, a.get("category", "")))
        cat_label = CATEGORY_LABEL.get(a.get("category", ""), a.get("category", cat))
        mark = "ok" if a.get("passed") else "no"
        sym = "✓" if a.get("passed") else "✕"
        items.append(
            f'<li><span class="assert-mark {mark}">{sym}</span>'
            f'<span><div class="assert-name">{esc(label)}{_assert_id_badge(label, name)}</div>'
            f'<div class="assert-detail">{esc(a.get("detail", ""))}</div></span>'
            f'<span class="assert-cat">{esc(cat_label)}</span></li>'
        )
    if not items:
        return '<li class="empty" style="padding:16px;color:var(--ink-faint)">기록된 판정 항목 없음</li>'
    return "".join(items)


def build_judge_panel(judge: dict | None) -> str:
    if judge is None:
        return (
            '<div class="panel-head"><h2>LLM Judge 평가</h2></div>'
            '<p class="no-judge">이 실행에는 Judge 호출 기록이 없다 — 판정 계약 미연결이거나 아직 실행 전이다.</p>'
        )
    j = judge.get("judge", {})
    verdict = j.get("verdict", {})
    overall = verdict.get("overall_verdict", "UNCERTAIN")
    overall_cls = STATUS_CLASS.get(overall, "uncertain") if overall in STATUS_CLASS else (
        "fail" if overall == "FAIL" else "pass" if overall == "PASS" else "uncertain"
    )
    dims_html = []
    for name, d in (verdict.get("dimensions") or {}).items():
        label, _ = ASSERTION_GLOSSARY.get(name, (name, ""))
        v = (d.get("verdict") or "uncertain").lower()
        chips = "".join(f'<span class="evidence-chip">{esc(r)}</span>' for r in (d.get("evidence_refs") or []))
        dims_html.append(
            f'<div class="dim-card"><div class="dim-head">'
            f'<span class="dim-name">{esc(label)}{_assert_id_badge(label, name)}</span>'
            f'<span class="verdict-tag {v}">{esc(VERDICT_LABEL.get(v, v))}</span></div>'
            f'<div class="dim-reason">{esc(d.get("reason", ""))}</div>'
            f'<div class="evidence-row">{chips}</div></div>'
        )
    meta = j.get("usage", {})
    return (
        '<div class="panel-head"><h2>LLM Judge 평가</h2>'
        f'<span class="verdict-tag {overall_cls}">{esc(VERDICT_LABEL.get(overall, overall))}</span></div>'
        '<div class="judge-summary">'
        f'<p>{esc(verdict.get("summary", ""))}</p>'
        '<div class="judge-meta">'
        f'<span><b>{esc(j.get("model", ""))}</b></span>'
        f'<span>프롬프트 <b>{esc(j.get("prompt_version", ""))}</b></span>'
        f'<span>지연시간 <b>{fmt_ms(j.get("latency_ms"))}</b></span>'
        f'<span>토큰 <b>{meta.get("total_tokens", "미측정")}</b></span>'
        "</div></div>"
        f'<div class="dim-list">{"".join(dims_html)}</div>'
        '<p class="callout">참고용(REPORT_ONLY) — 이 판정은 참고용 보조 채점이며 왼쪽의 결정론적 판정을 뒤집지 않는다.</p>'
    )


_DATASET_INPUT_BY_ID: dict[str, str] | None = None


def _dataset_input_by_id() -> dict[str, str]:
    """데이터셋의 `case.id → input` 사전을 한 번만 읽어 캐시한다.

    2026-08-27 이전에 기록된 case는 `input`을 저장하지 않았다(러너가 아직
    복사하지 않았음). 그 case들도 화면에서 사용자 요청을 볼 수 있도록,
    같은 데이터셋 파일에서 원문 `input`을 찾아 보여준다 — case_id가
    반복·재시도로 `-R1`, `-CLEAN-R1`처럼 접미사가 붙어도 원래 데이터셋
    case_id로 시작하면 같은 입력으로 본다.
    """
    global _DATASET_INPUT_BY_ID
    if _DATASET_INPUT_BY_ID is None:
        from services.evaluation import load_workflow_dataset

        dataset = load_workflow_dataset(DEFAULT_DATASET)
        _DATASET_INPUT_BY_ID = {
            c["id"]: c["input"] for c in dataset.get("cases", []) if c.get("input")
        }
    return _DATASET_INPUT_BY_ID


def _recover_input_from_dataset(case_id: str) -> str | None:
    for dataset_id, inp in _dataset_input_by_id().items():
        if case_id == dataset_id or case_id.startswith(dataset_id + "-"):
            return inp
    return None


def build_request_block(case: dict, manifest: dict) -> str:
    inp = case.get("input") or manifest.get("input")
    if not inp:
        inp = _recover_input_from_dataset(case.get("case_id", ""))
    if inp:
        return f'<div class="request-block"><span class="who">사용자 요청</span>{esc(inp)}</div>'
    return ""


def build_answer_or_rubric(case: dict) -> tuple[str, str, str]:
    """(mount용 markdown 원문, 대체 HTML, 정적 안내 문구) 3튜플.

    안내 문구는 answer-mount **밖**에 고정 HTML로 넣는다 — mount 안은 JS가
    renderMarkdown() 결과로 통째로 덮어써서, 안에 넣으면 로드 즉시 지워진다.

    `eval_case_result.result`에 `final_answer`가 없는 옛날 case(사람이
    rubric만 남기던 시절 기록)만 `agent_run_id`로 실제 채팅 기록에서 복구를
    시도한다 — `eval_record.py --fill-from-db`가 기록 시점에 이미 채운
    case는 이 복구 경로를 안 탄다.
    """
    final_answer = case.get("final_answer")
    if not final_answer and case.get("agent_run_id"):
        from backend.db.evaluation import EvaluationResultRepository

        summary = EvaluationResultRepository.fetch_agent_execution_summary(
            case["agent_run_id"]
        )
        final_answer = summary["final_answer"]
        if final_answer:
            notice = (
                '<p class="panel-note" style="padding:10px 24px 0">'
                "DB에 최종 답변이 없어 제품 DB의 실제 채팅 기록에서 복구함</p>"
            )
            return final_answer, "", notice
    if final_answer:
        return final_answer, "", ""
    rubric = case.get("human_rubric")
    note = case.get("review_note")
    parts = []
    if rubric:
        parts.append(f"<p><b>사람 평가 rubric</b>: {esc(json.dumps(rubric, ensure_ascii=False))}</p>")
    if note:
        parts.append(f"<p><b>검토 메모</b>: {esc(note)}</p>")
    if not parts:
        parts.append('<p class="empty">기록된 최종 답변·검토 메모가 없고, DB에서도 복구되지 않았다(세션 삭제 등).</p>')
    return "", "".join(parts), ""


def render_case_page(manifest: dict, case: dict, judge: dict | None) -> str:
    case_id = case.get("case_id", "UNKNOWN")
    status = case.get("status", "UNKNOWN")
    status_cls = case_status_class(case)
    failure_reason = case.get("failure_reason")
    assertions = case.get("assertions") or []
    passed = sum(1 for a in assertions if a.get("passed"))
    answer_md, answer_fallback, answer_notice = build_answer_or_rubric(case)

    status_text = STATUS_LABEL.get(status, status)
    if failure_reason:
        status_text += f" · {esc(failure_reason)}"

    html_parts = [
        "<title>평가 케이스 · " + esc(case_id) + "</title>",
        f"<style>{PAGE_CSS}</style>",
        '<div class="wrap">',
        '<a class="back-link" href="../index.html">&larr; 전체 목록으로</a>',
        '<header class="case-header"><div>',
        f'<p class="eyebrow">평가 케이스 파일 · {esc(case_id)}</p>',
        f"<h1>{esc(case_id)}</h1>",
        '<div class="chip-row">',
        f'<span class="chip">에이전트 <b>{esc(case.get("agent_id",""))} / {esc(case.get("agent_version_id",""))}</b></span>',
        f'<span class="chip">모델 <b>{esc(case.get("model",""))}</b></span>',
        f'<span class="chip">런타임 <b>{esc(case.get("runtime",""))}</b></span>',
        f'<span class="chip">데이터셋 <b>{esc(case.get("dataset_id",""))} v{esc(case.get("dataset_version",""))}</b></span>',
        "</div></div>",
        f'<span class="status-pill {status_cls}">{status_text}</span>',
        "</header>",
    ]

    req = build_request_block(case, manifest)
    if req:
        html_parts += ['<section><p class="section-label">사용자 요청</p>', req, "</section>"]

    html_parts += [
        '<section><p class="section-label">실행 지표</p>',
        build_metric_tiles(case.get("metrics") or {}),
        "</section>",
        '<div class="split">',
        '<div class="panel area-answer"><div class="panel-head"><h2>최종 답변</h2>',
        '<span class="panel-note">에이전트 원문 · 마스킹 없음(사내 평가용)</span></div>',
        answer_notice,
        f'<div class="answer-body" id="answer-mount">{answer_fallback}</div></div>',
        '<div class="panel area-judge">',
        build_judge_panel(judge),
        "</div>",
        '<div class="panel area-assert"><div class="panel-head"><h2>결정론적 판정</h2>',
        f'<span class="panel-note">코드 판정 항목 · {passed} / {len(assertions)} 통과</span></div>',
        f'<ul class="assert-list">{build_assert_list(assertions)}</ul></div>',
        "</div>",
        '<div class="provenance">',
        f'<span><b>평가 실행(eval_run)</b> {esc(case.get("eval_run_id",""))}</span>',
        f'<span><b>에이전트 실행(agent_run)</b> {esc(case.get("agent_run_id",""))}</span>',
        f'<span><b>실행 시각</b> {esc(case.get("started_at",""))}</span>',
        f'<span><b>정리 상태</b> {esc((case.get("cleanup") or {}).get("status",""))}</span>',
        "</div></div>",
    ]

    if answer_md:
        html_parts += [
            "<script>",
            MARKDOWN_JS,
            f'document.getElementById("answer-mount").innerHTML = renderMarkdown({js_str(answer_md)});',
            "</script>",
        ]

    return "\n".join(p for p in html_parts if p)


def main() -> None:
    _ensure_django()
    CASES_DIR.mkdir(parents=True, exist_ok=True)

    index_rows = []
    for run in fetch_all_runs():
        eval_run_id = run["eval_run_id"]
        manifest = run["manifest"] or {}
        for row in fetch_cases_for_run(eval_run_id):
            case_index = row["case_index"]
            case = row["result"]
            judge = fetch_judge_for_case(eval_run_id, case_index)
            out_name = f"{eval_run_id}__{case_index}.html"
            page = render_case_page(manifest, case, judge)
            (CASES_DIR / out_name).write_text(page, encoding="utf-8")

            status = case.get("status", "UNKNOWN")
            index_rows.append({
                "run": eval_run_id,
                "case_id": case.get("case_id", "?"),
                "status": status,
                "status_cls": case_status_class(case),
                "has_judge": judge is not None,
                "started_at": case.get("started_at", ""),
                "file": out_name,
                "dataset": f'{case.get("dataset_id","")} v{case.get("dataset_version","")}',
            })

    index_rows.sort(key=lambda r: r["started_at"])

    rows_html = []
    for r in index_rows:
        judge_mark = '<span class="judge-dot" title="Judge 결과 있음"></span>Judge' if r["has_judge"] else '<span style="color:var(--ink-faint)">—</span>'
        rows_html.append(
            "<tr>"
            f'<td><a href="cases/{r["file"]}">{esc(r["case_id"])}</a></td>'
            f'<td><span class="pill-sm {r["status_cls"]}">{esc(STATUS_LABEL.get(r["status"], r["status"]))}</span></td>'
            f'<td class="mono-cell">{esc(r["dataset"])}</td>'
            f'<td>{judge_mark}</td>'
            f'<td class="mono-cell">{esc(r["started_at"])}</td>'
            f'<td class="mono-cell">{esc(r["run"])}</td>'
            "</tr>"
        )

    index_html = "\n".join([
        "<title>평가 시나리오 전체 목록</title>",
        f"<style>{PAGE_CSS}</style>",
        '<div class="wrap">',
        '<header class="case-header"><div>',
        '<p class="eyebrow">지금까지 실행한 평가</p>',
        f"<h1>평가 시나리오 전체 목록 ({len(index_rows)}건)</h1>",
        "</div></header>",
        '<table class="index-table"><thead><tr>'
        "<th>케이스</th><th>상태</th><th>데이터셋</th><th>Judge</th><th>실행 시각</th><th>eval_run_id</th>"
        "</tr></thead><tbody>",
        "\n".join(rows_html),
        "</tbody></table></div>",
    ])
    (REPORT_DIR / "index.html").write_text(index_html, encoding="utf-8")

    index_path = (REPORT_DIR / "index.html").resolve()
    print(f"생성 완료: {index_path}  (케이스 {len(index_rows)}건)")
    try:
        webbrowser.open(index_path.as_uri())
    except Exception:
        # Docker 컨테이너 안에서 돌리면(DB 복구를 쓰려면 여기서 실행해야 한다)
        # 브라우저가 없다 — 위 경로를 호스트에서 그대로 열면 된다(같은 저장소
        # 루트가 volume mount라 호스트 경로와 내용이 같다).
        print("브라우저를 자동으로 열지 못했다 — 위 경로를 호스트에서 직접 열어라.")


if __name__ == "__main__":
    main()
