"""Drive 변경 알림 채널의 생명주기.

**채널은 스스로 갱신되지 않는다.** Drive 의 `changes` 채널은 최대 1주이고
만료되면 그냥 조용해진다 — 알림이 안 오는 것과 「바뀐 게 없는 것」이 화면에서
구별되지 않으므로, 만료 전에 새로 여는 일을 누군가는 해야 한다. 그 일을
`manage.py renew_drive_channels` 가 하고, 서버의 cron 이 그것을 부른다.

여기에는 그 커맨드와 커넥터 화면이 함께 쓰는 **여닫는 절차**만 둔다.

## 웹훅이 없어도 돌아간다

`GOOGLE_DRIVE_WEBHOOK_URL`·`GOOGLE_DRIVE_WEBHOOK_TOKEN` 이 비어 있으면 아무것도
하지 않는다. 로컬처럼 Google 이 닿을 수 없는 곳에서는 그것이 정상이고, 그때는
예전처럼 **대화를 시작할 때** 도는 동기화가 받친다(`apps/chat/api_views.py`).
웹훅은 그 위에 얹는 것이지 대체하는 것이 아니다.
"""

from __future__ import annotations

import logging
from datetime import datetime

from django.conf import settings

from backend.db import ConnectorRepository

from .clients import drive_start_page_token, stop_drive_channel, watch_drive_changes
from .oauth import OAuthError

logger = logging.getLogger(__name__)


def webhook_enabled() -> bool:
    """주소와 비밀값이 **둘 다** 있어야 켠 것으로 본다.

    하나만 있으면 안 켠 것으로 다룬다 — 주소만 있고 토큰이 없으면 콜백이 아무나
    두드릴 수 있는 문이 되고, 토큰만 있으면 채널을 열 곳이 없다.
    """

    return bool(settings.GOOGLE_DRIVE_WEBHOOK_URL and settings.GOOGLE_DRIVE_WEBHOOK_TOKEN)


def open_channel(*, conn_id: str, account_id: str, sync_cursor: str | None) -> bool:
    """이 연결에 새 채널을 연다. 열었으면 `True`.

    **옛 채널을 먼저 멈춘다.** 갈아탈 때 안 멈추면 만료까지 둘이 함께 알림을
    보내고, 우리는 같은 변경을 두 번 처리한다(해롭진 않지만 값이 두 배다).

    커서가 없으면 지금 시점을 받아 함께 저장한다. 채널은 「이 지점 이후」를
    감시하는 것이라 시작점이 있어야 한다.
    """

    if not webhook_enabled():
        return False

    try:
        cursor_value = sync_cursor or drive_start_page_token(account_id=account_id)
        result = watch_drive_changes(
            account_id=account_id,
            page_token=cursor_value,
            callback_url=settings.GOOGLE_DRIVE_WEBHOOK_URL,
            token=settings.GOOGLE_DRIVE_WEBHOOK_TOKEN,
        )
    except OAuthError as exc:
        # **채널을 못 열어도 연결은 산다.** 대화 시작 동기화가 받치므로 문서가
        # 안 들어오는 것은 아니다 — 다음 갱신 회차가 다시 시도한다.
        logger.warning("Drive 채널을 열지 못했습니다: conn=%s (%s)", conn_id, exc)
        return False

    if not sync_cursor:
        ConnectorRepository.set_sync_cursor(conn_id=conn_id, cursor_value=cursor_value)
    ConnectorRepository.set_watch_channel(
        conn_id=conn_id,
        channel_id=result["channel_id"],
        resource_id=result["resource_id"],
        expires_at=result["expires_at"],
    )
    return True


def close_channel(*, conn_id: str, account_id: str, channel_id: str | None, resource_id: str | None) -> None:
    """채널을 멈추고 기록을 지운다. **둘은 항상 짝이다.**

    기록만 지우면 살아 있는 채널이 계속 알림을 보내는데 우리는 그것이 무엇인지
    모른다. 멈추기만 하면 갱신 작업이 죽은 채널을 살아 있는 것으로 본다.
    """

    if channel_id and resource_id:
        stop_drive_channel(account_id=account_id, channel_id=channel_id, resource_id=resource_id)
    ConnectorRepository.set_watch_channel(
        conn_id=conn_id, channel_id=None, resource_id=None, expires_at=None
    )


def renew_expiring(*, before: datetime) -> dict[str, int]:
    """`before` 이전에 만료되는 채널을 새로 연다. 갱신 커맨드가 부른다.

    아직 채널이 없는 연결도 함께 잡힌다 — 웹훅을 켜기 전에 연결해 둔 팀과, 한
    번 실패한 팀이 여기서 따라붙는다.
    """

    if not webhook_enabled():
        return {"checked": 0, "opened": 0, "failed": 0}

    rows = ConnectorRepository.channels_needing_renewal(before)
    opened = 0
    for row in rows:
        close_channel(
            conn_id=row["conn_id"],
            account_id=row["account_id"],
            channel_id=row.get("channel_id"),
            resource_id=row.get("channel_resource_id"),
        )
        if open_channel(
            conn_id=row["conn_id"],
            account_id=row["account_id"],
            sync_cursor=row.get("sync_cursor"),
        ):
            opened += 1
    return {"checked": len(rows), "opened": opened, "failed": len(rows) - opened}

