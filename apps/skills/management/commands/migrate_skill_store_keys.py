"""일회성 데이터 이관 — 절대경로로 저장된 스킬 Store 키를 상대경로로 고친다.

2026-08-26 발견한 버그(`services/agent_runtime/skills/service.py::_store_backend()`
docstring 참고)의 데이터 쪽 뒷정리다. 그 버그를 고치기 **전에** 쓰인 모든
스킬(`skill_register`/설정 화면으로 만든 개인·팀 스킬, 내장 스킬 씨딩분)은
Store에 `/skills/{scope}/{name}/SKILL.md`(절대경로)를 키로 갖고 있다 —
`CompositeBackend`가 실제 그래프에서 이 키를 찾을 때는 항상 prefix를 뗀
`/{name}/SKILL.md`(상대경로)로 찾으므로, 코드를 고쳐도 **이미 저장된
행**은 계속 안 보인다. 이 커맨드가 기존 행을 상대경로 키로 옮겨 쓰고 옛
키를 지운다 — 새로 쓰는 스킬은 고친 코드가 이미 상대경로로 쓰므로 이
커맨드를 다시 돌릴 필요가 없다(멱등적이긴 하다 — 상대경로 키만 있으면
그냥 건너뛴다).
"""

from __future__ import annotations

import os

from django.core.management.base import BaseCommand

ABS_PREFIXES = ["/skills/builtin/", "/skills/personal/", "/skills/team/"]


class Command(BaseCommand):
    help = "절대경로로 저장된 스킬 Store 키를 CompositeBackend가 찾는 상대경로로 이관한다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="옮기지 않고 무엇을 옮길지만 보여준다.",
        )

    def handle(self, *args, **options):
        import psycopg

        from services.agent_runtime.memory.store import get_memory_store

        dry_run: bool = options["dry_run"]
        store = get_memory_store()

        conn_str = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://")
        with psycopg.connect(conn_str) as conn, conn.cursor() as cur:
            cur.execute("SELECT prefix, key FROM store WHERE prefix LIKE 'skill.%' ORDER BY prefix, key")
            rows = cur.fetchall()

        self.stdout.write(f"대상 {len(rows)}건 발견")
        migrated = 0
        skipped = 0
        for prefix, key in rows:
            namespace = tuple(prefix.split("."))
            matched = next((p for p in ABS_PREFIXES if key.startswith(p)), None)
            if matched is None:
                self.stdout.write(f"  건너뜀(이미 상대경로): {namespace} {key}")
                skipped += 1
                continue

            new_key = key[len(matched) - 1 :]  # 맨 앞 '/'는 남긴다
            if dry_run:
                self.stdout.write(f"  [dry-run] {namespace} {key} -> {new_key}")
                migrated += 1
                continue

            item = store.get(namespace, key)
            if item is None:
                self.stdout.write(self.style.WARNING(f"  읽기 실패, 건너뜀: {namespace} {key}"))
                continue

            if store.get(namespace, new_key) is not None:
                self.stdout.write(f"  새 키가 이미 있어 옛 키만 지움: {namespace} {key}")
                store.delete(namespace, key)
                migrated += 1
                continue

            store.put(namespace, new_key, item.value)
            store.delete(namespace, key)
            self.stdout.write(f"  이관: {namespace} {key} -> {new_key}")
            migrated += 1

        self.stdout.write(self.style.SUCCESS(f"완료. 이관={migrated} 건너뜀={skipped}"))
