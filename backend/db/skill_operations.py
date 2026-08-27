"""스킬 카탈로그 revision과 검증 워커 운영 상태 저장소."""

from __future__ import annotations

from .connection import database_connection


class SkillCatalogRevisionRepository:
    @staticmethod
    def get(account_id: str) -> int:
        with database_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT revision FROM skill_catalog_revision WHERE account_id = %s", (account_id,))
            row = cursor.fetchone()
        return int(row["revision"]) if row else 0

    @staticmethod
    def increment(account_id: str) -> int:
        with database_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO skill_catalog_revision (account_id, revision)
                VALUES (%s, 1)
                ON CONFLICT (account_id) DO UPDATE
                   SET revision = skill_catalog_revision.revision + 1, updated_at = now()
                RETURNING revision
                """,
                (account_id,),
            )
            return int(cursor.fetchone()["revision"])


class SkillWorkerHeartbeatRepository:
    @staticmethod
    def touch(worker_id: str) -> None:
        with database_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO skill_worker_heartbeat (worker_id) VALUES (%s)
                ON CONFLICT (worker_id) DO UPDATE SET heartbeat_at = now()
                """,
                (worker_id,),
            )

    @staticmethod
    def active_count(*, ttl_seconds: int) -> int:
        with database_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*) AS count FROM skill_worker_heartbeat
                 WHERE heartbeat_at >= now() - (%s || ' seconds')::interval
                """,
                (ttl_seconds,),
            )
            return int(cursor.fetchone()["count"])


__all__ = ["SkillCatalogRevisionRepository", "SkillWorkerHeartbeatRepository"]
