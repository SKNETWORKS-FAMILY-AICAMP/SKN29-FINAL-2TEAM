"""문서를 사람 손 없이 받아들이는 자리.

**「이 문서를 파싱/임베딩 하겠다」를 사람이 정하지 않는다**(2026-08-15 PM).
사람이 하는 일은 저장소를 연결하고 어떤 폴더를 볼지 정하는 것까지고, 그 뒤는
전부 시스템이 판단한다 —

    커넥터 폴더 → 목록 확보 → 내려받기 → 요약·메타 → 파싱·임베딩

네 단계가 전에는 API 뷰 넷에 흩어져 있었고 **화면이 문서마다 이어 부르며**
진행을 보여줬다(`TeamDocumentMetaAPIView` 주석). 그 화면(`/files/new`)은
사람이 파일을 고르는 옛 모델이라 걷어냈고, 걷어내고 나니 이 사슬을 부르는
주체가 아무도 없었다 — `doc` 이 0건이라 검색이 아예 성립하지 않았다.

여기는 **본문 색인까지** 한다. 한동안 요약에서 멈추고 청크 파싱·임베딩은
검색이 좁힌 문서에만 돌렸는데(2026-08-15 PM), 그러면 폴더에 있는데도 문장
근거를 낼 수 없는 문서가 계속 남는다. 「연결된 폴더를 검색한다」고 말하는
이상 권한 범위 안의 문서는 결국 전부 색인되어 있어야 한다.

요약 단계는 같은 날 통째로 없앴다 — 전량 색인이 있으면 요약으로 좁힐 이유가
없고, 색인된 본문에서 직접 찾는 쪽이 정확하다.

동기화 시점은 둘이다. **폴더를 저장할 때**는 전체를 훑어 새 문서를 등록하고
(`intake_connector_documents`), **대화를 시작할 때**는 Drive Changes API 로
변경분만 따라간다(`sync_drive_changes`). 뒤엣것은 변화가 없으면 호출 1번이라
자주 돌아도 부담이 없다.
"""

from .service import (
    IntakeResult,
    intake_connector_documents,
    LONG_PROMOTE_WAIT_SECONDS,
    promote_to_searchable,
    sync_drive_changes,
)

__all__ = [
    "IntakeResult",
    "intake_connector_documents",
    "LONG_PROMOTE_WAIT_SECONDS",
    "promote_to_searchable",
    "sync_drive_changes",
]
