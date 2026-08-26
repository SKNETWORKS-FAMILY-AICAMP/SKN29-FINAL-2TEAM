"""이미 다 읽은 **커넥터 문서의 원문**을 저장소에서 지운다. 한 번 돌리는 정리다.

2026-08-26 에 「커넥터가 가져온 원본은 들고 있지 않는다」로 바꿨다. 원본은 Drive
에 있고 우리는 사본이라, 청크와 임베딩을 만들고 나면 보관할 이유가 없다. 색인이
끝나는 자리에서 곧바로 버리도록 고쳤지만(`services/document_intake` 의
`_discard_original`), **그 전에 색인된 문서는 원문을 그대로 들고 있다.** 이
스크립트가 그것들을 훑는다.

**올린 파일(「문서 > 내 파일」)은 건드리지 않는다.** 그쪽은 원본이 우리뿐이라
지우면 되돌릴 곳이 없다 — `src_file_id` 가 있는 것만 고르는 이유다.

지워도 잃는 것이 없다. `content_hash`·`cur_revision` 은 칸에 남으므로 변경 감지가
그대로 돌고, 다시 읽어야 하면 Drive 에서 받아 온다(`_refetch_original`).

Django 관리 커맨드로 만들지 않은 이유는 `renew_drive_channels.py` 와 같다 — 이
저장소는 앱을 `INSTALLED_APPS` 에 등록하지 않아서 커맨드가 발견되지 않는다.

    # 무엇이 지워질지 먼저 본다 (아무것도 안 지운다)
    docker compose -f infra/docker/docker-compose.aws.yml exec -T web \
      python scripts/purge_indexed_originals.py --dry-run

    # 실제로 지운다
    docker compose -f infra/docker/docker-compose.aws.yml exec -T web \
      python scripts/purge_indexed_originals.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Windows 콘솔은 기본이 cp949 라 한글이 깨져 나간다(`_apply.py` 와 같은 이유).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

import django  # noqa: E402

django.setup()

from backend.db import DocumentRepository  # noqa: E402
from backend.services import storage  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="무엇이 지워질지만 보여주고 아무것도 지우지 않는다.",
    )
    args = parser.parse_args()

    targets = DocumentRepository.list_discardable_originals()
    if not targets:
        print("정리할 원문이 없습니다.")
        return 0

    print(f"대상 {len(targets)}건")
    removed = failed = 0
    for target in targets:
        name = target["file_name"] or target["doc_id"]
        if args.dry_run:
            print(f"  [그대로 둠] {target['doc_id']} · {name} · {target['storage_key']}")
            continue
        try:
            # **파일을 먼저 지우고 칸을 비운다.** 반대 순서면 지우다 실패했을 때
            # 「DB 는 없다는데 파일은 남은」 상태가 되고, 그 파일은 다시 찾을
            # 방법이 없어 영영 남는다.
            storage.remove(target["storage_key"])
            DocumentRepository.clear_stored_original(target["doc_id"])
            removed += 1
        except Exception as exc:  # noqa: BLE001 — 한 건이 나머지를 멈추지 않는다
            failed += 1
            print(f"  [실패] {target['doc_id']} · {name} · {exc.__class__.__name__}: {exc}")

    if args.dry_run:
        print("--dry-run 이라 아무것도 지우지 않았습니다.")
    else:
        print(f"지운 것 {removed}건 · 실패 {failed}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
