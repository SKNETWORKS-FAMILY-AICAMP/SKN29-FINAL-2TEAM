"""완료된 Agent 평가 파일 계약을 DB 조회·집계 사본으로 동기화한다."""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .connection import database_connection


class EvaluationResultRepository:
    """같은 ``eval_run_id``를 다른 내용으로 덮어쓰지 않는 평가 저장소."""

    @staticmethod
    def sync_completed_run(
        *,
        manifest: dict[str, Any],
        case_results: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        eval_run_id = str(manifest["eval_run_id"])
        if summary.get("eval_run_id") != eval_run_id:
            raise ValueError("summary의 eval_run_id가 manifest와 다릅니다.")

        EvaluationResultRepository._ensure_pending_run(
            manifest=manifest,
            summary=summary,
        )
        EvaluationResultRepository._sync_cases_and_complete(
            eval_run_id=eval_run_id,
            case_results=case_results,
            summary=summary,
        )
        return {
            "eval_run_id": eval_run_id,
            "case_count": len(case_results),
            "sync_status": "SYNCED",
        }

    @staticmethod
    def _ensure_pending_run(
        *, manifest: dict[str, Any], summary: dict[str, Any]
    ) -> None:
        eval_run_id = str(manifest["eval_run_id"])
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO eval_run (
                        eval_run_id, schema_version, git_commit,
                        dataset_id, dataset_version, runtime, environment,
                        repetitions, run_status, sync_status,
                        started_at, finished_at, manifest, summary
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, 'SYNC_PENDING', %s, %s, %s, %s
                    )
                    ON CONFLICT (eval_run_id) DO NOTHING
                    RETURNING eval_run_id
                    """,
                    (
                        eval_run_id,
                        manifest["schema_version"],
                        manifest["git_commit"],
                        manifest["dataset_id"],
                        str(manifest["dataset_version"]),
                        manifest["runtime"],
                        manifest["environment"],
                        manifest["repetitions"],
                        summary["run_status"],
                        manifest["started_at"],
                        summary["finished_at"],
                        Jsonb(manifest),
                        Jsonb(summary),
                    ),
                )
                if cursor.fetchone() is not None:
                    return

                cursor.execute(
                    "SELECT manifest, summary FROM eval_run WHERE eval_run_id = %s",
                    (eval_run_id,),
                )
                existing = cursor.fetchone()
                if existing is None:
                    raise RuntimeError("동기화 중인 평가 실행을 다시 읽지 못했습니다.")
                if existing["manifest"] != manifest or existing["summary"] != summary:
                    raise ValueError(
                        "같은 eval_run_id에 다른 평가 결과가 이미 저장되어 있습니다."
                    )

    @staticmethod
    def _sync_cases_and_complete(
        *,
        eval_run_id: str,
        case_results: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> None:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                for case_index, result in enumerate(case_results, start=1):
                    if result.get("eval_run_id") != eval_run_id:
                        raise ValueError(
                            f"{case_index}번째 case의 eval_run_id가 manifest와 다릅니다."
                        )
                    cursor.execute(
                        """
                        INSERT INTO eval_case_result (
                            eval_run_id, case_index, case_id,
                            agent_id, agent_version_id, model, runtime, status,
                            started_at, finished_at, agent_run_id,
                            langfuse_trace_id, metrics, result
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (eval_run_id, case_index) DO NOTHING
                        RETURNING case_index
                        """,
                        (
                            eval_run_id,
                            case_index,
                            result["case_id"],
                            result["agent_id"],
                            result["agent_version_id"],
                            result["model"],
                            result["runtime"],
                            result["status"],
                            result["started_at"],
                            result["finished_at"],
                            result.get("agent_run_id"),
                            result.get("langfuse_trace_id"),
                            Jsonb(result["metrics"]),
                            Jsonb(result),
                        ),
                    )
                    if cursor.fetchone() is not None:
                        continue

                    cursor.execute(
                        """
                        SELECT result
                        FROM eval_case_result
                        WHERE eval_run_id = %s AND case_index = %s
                        """,
                        (eval_run_id, case_index),
                    )
                    existing = cursor.fetchone()
                    if existing is None or existing["result"] != result:
                        raise ValueError(
                            "같은 eval_run_id/case_index에 다른 결과가 이미 저장되어 있습니다."
                        )

                cursor.execute(
                    """
                    UPDATE eval_run
                    SET run_status = %s,
                        finished_at = %s,
                        summary = %s,
                        sync_status = 'SYNCED',
                        synced_at = now()
                    WHERE eval_run_id = %s
                    """,
                    (
                        summary["run_status"],
                        summary["finished_at"],
                        Jsonb(summary),
                        eval_run_id,
                    ),
                )

    @staticmethod
    def sync_judge_result(record: dict[str, Any]) -> dict[str, Any]:
        """`judge_calibration.jsonl`의 레코드 한 줄을 `eval_judge_result`에 동기화한다.

        `case_id`가 아니라 `agent_run_id`로 대상 `eval_case_result`의
        `case_index`를 찾는다 — 같은 case_id가 한 실행 안에서 여러 번
        반복될 수 있어서(다른 표와 같은 이유), case_id만으로는 어느 반복인지
        구분할 수 없다. `human_verdict`/`comparison`은 calibration 표본일 때만
        있는 값이라 없으면 NULL로 둔다 — 지어내지 않는다.
        """
        eval_run_id = str(record["eval_run_id"])
        agent_run_id = record.get("agent_run_id")
        judge = record["judge"]
        human_verdict = record.get("human_verdict")
        comparison = record.get("comparison")

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT case_index FROM eval_case_result
                    WHERE eval_run_id = %s AND agent_run_id = %s
                    """,
                    (eval_run_id, agent_run_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise ValueError(
                        "이 agent_run_id에 대응하는 eval_case_result의 "
                        "case_index를 찾지 못했습니다 — case 동기화를 먼저 하세요."
                    )
                case_index = row["case_index"]

                cursor.execute(
                    """
                    INSERT INTO eval_judge_result (
                        eval_run_id, case_index, judge_model, prompt_version,
                        mode, latency_ms, usage, verdict,
                        human_verdict, comparison
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (eval_run_id, case_index, judge_model, prompt_version)
                    DO NOTHING
                    RETURNING case_index
                    """,
                    (
                        eval_run_id,
                        case_index,
                        judge["model"],
                        judge["prompt_version"],
                        record.get("mode", "REPORT_ONLY"),
                        judge.get("latency_ms"),
                        Jsonb(judge.get("usage")),
                        Jsonb(judge["verdict"]),
                        Jsonb(human_verdict) if human_verdict is not None else None,
                        Jsonb(comparison) if comparison is not None else None,
                    ),
                )
                if cursor.fetchone() is not None:
                    return {
                        "eval_run_id": eval_run_id,
                        "case_index": case_index,
                        "sync_status": "SYNCED",
                    }

                cursor.execute(
                    """
                    SELECT verdict FROM eval_judge_result
                    WHERE eval_run_id = %s AND case_index = %s
                      AND judge_model = %s AND prompt_version = %s
                    """,
                    (eval_run_id, case_index, judge["model"], judge["prompt_version"]),
                )
                existing = cursor.fetchone()
                if existing is None or existing["verdict"] != judge["verdict"]:
                    raise ValueError(
                        "같은 실행·case·Judge·프롬프트에 다른 결과가 이미 "
                        "저장되어 있습니다."
                    )
                return {
                    "eval_run_id": eval_run_id,
                    "case_index": case_index,
                    "sync_status": "SYNCED",
                }

    @staticmethod
    def fetch_agent_execution_summary(agent_run_id: str) -> dict[str, Any]:
        """사람이 UI로 실행한 case를 기록할 때 최종 답변·도구 호출을 손으로
        옮겨 적지 않아도 되게, 실제 실행된 agent_run의 결과를 제품 DB에서
        조회한다.

        세션이 없거나 지워졌으면(자동 runner의 임시 세션 정리 등) 빈 값을
        돌려준다 — 이 조회는 있으면 좋은 보강이지, 없다고 기록 자체를
        막지 않는다.
        """
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT session_id FROM agent_run WHERE run_id = %s",
                    (agent_run_id,),
                )
                row = cursor.fetchone()
                session_id = row["session_id"] if row else None

                final_answer = None
                if session_id:
                    cursor.execute(
                        "SELECT content FROM chat_message "
                        "WHERE session_id = %s AND role = 'agent' "
                        "ORDER BY created_at",
                        (session_id,),
                    )
                    for message in cursor.fetchall():
                        content = message.get("content") or {}
                        if isinstance(content, dict) and content.get("text"):
                            final_answer = content["text"]

                cursor.execute(
                    "SELECT tool_call_id FROM tool_call "
                    "WHERE run_id = %s ORDER BY created_at",
                    (agent_run_id,),
                )
                tool_call_ids = [str(r["tool_call_id"]) for r in cursor.fetchall()]

        return {"final_answer": final_answer, "tool_call_ids": tool_call_ids}


__all__ = ["EvaluationResultRepository"]
