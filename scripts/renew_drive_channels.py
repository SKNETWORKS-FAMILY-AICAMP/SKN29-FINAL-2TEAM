"""Drive 변경 알림 채널을 만료 전에 새로 연다. **cron 이 부른다.**

`changes.watch` 로 연 채널은 **스스로 갱신되지 않고** 최대 1주면 끝난다. 만료
되면 알림이 그냥 끊기는데, 화면에서 「알림이 안 온다」와 「바뀐 게 없다」는
구별되지 않는다 — 조용히 낡아 가는 것이 여기서 가장 나쁜 실패다.

Django 관리 커맨드로 만들지 않은 이유: 이 저장소는 앱을 `INSTALLED_APPS` 에
등록하지 않는다(`DATABASES = {}`, ORM 을 안 쓴다). 그래서 관리 커맨드가 발견
되지 않는다. `DB/migrations/_apply.py` 와 같은 **단독 스크립트** 관례를 따른다.

    # 서버(EC2)에서
    cd ~/SKN29-Final-2Team
    docker compose -f infra/docker/docker-compose.aws.yml exec -T web \
      python scripts/renew_drive_channels.py

    # cron — 하루 한 번
    0 4 * * * cd ~/SKN29-Final-2Team && docker compose -f infra/docker/docker-compose.aws.yml \
      exec -T web python scripts/renew_drive_channels.py >> /var/log/halil-drive-renew.log 2>&1

채널 수명을 6일로 잡아 두었으므로(`clients.DRIVE_CHANNEL_TTL`), **하루치 실행을
한 번쯤 걸러도 채널이 살아 있다.** 상한(7일)에 딱 맞추지 않은 이유가 이것이다.

웹훅을 안 켠 배포에서는 아무것도 하지 않고 끝난다 — 로컬처럼 Google 이 닿을 수
없는 곳에서는 그것이 정상이고, 그때는 대화 시작 시 동기화가 받친다.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Windows 콘솔은 기본이 cp949 라 한글이 깨져 나간다(`_apply.py` 와 같은 이유).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

import django  # noqa: E402

django.setup()

from apps.connectors import watch  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--within-hours",
        type=int,
        default=48,
        help=(
            "몇 시간 안에 만료되는 채널까지 갱신할지. 기본 48 — 하루 한 번 도는데 "
            "24 로 잡으면 실행이 한 번 밀리는 순간 만료된 채로 남는다."
        ),
    )
    args = parser.parse_args()

    if not watch.webhook_enabled():
        print("웹훅이 꺼져 있어 아무것도 하지 않습니다(GOOGLE_DRIVE_WEBHOOK_URL·TOKEN 없음).")
        return 0

    before = datetime.now(UTC) + timedelta(hours=args.within_hours)
    result = watch.renew_expiring(before=before)
    print(
        f"대상 {result['checked']}건 · 새로 연 것 {result['opened']}건 · 실패 {result['failed']}건"
    )
    # **실패를 종료 코드로 올리지 않는다.** cron 이 부르는 자리라 비정상 종료가
    # 메일로 쌓이는데, 한 팀의 자격증명이 만료된 것은 다음 회차가 다시 시도하면
    # 되는 일이지 사람을 깨울 일이 아니다. 실패는 위 줄과 로그에 남는다.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
