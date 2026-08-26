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


__all__ = ["EvaluationResultRepository"]
