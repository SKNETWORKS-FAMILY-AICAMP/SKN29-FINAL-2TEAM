"""문서를 사람 손 없이 받아들이는 자리.

**「이 문서를 파싱/임베딩 하겠다」를 사람이 정하지 않는다**(2026-08-15 PM).
사람이 하는 일은 저장소를 연결하고 어떤 폴더를 볼지 정하는 것까지고, 그 뒤는
전부 시스템이 판단한다 —

    커넥터 폴더 → 목록 확보 → 내려받기 → 요약·메타 → (필요할 때) 파싱·임베딩

네 단계가 전에는 API 뷰 넷에 흩어져 있었고 **화면이 문서마다 이어 부르며**
진행을 보여줬다(`TeamDocumentMetaAPIView` 주석). 그 화면(`/files/new`)은
사람이 파일을 고르는 옛 모델이라 걷어냈고, 걷어내고 나니 이 사슬을 부르는
주체가 아무도 없었다 — `doc` 이 0건이라 검색이 아예 성립하지 않았다.

여기는 **요약까지**만 한다. 마지막 단계(청크 파싱·임베딩)는 무겁고 느려서
전 문서에 미리 돌릴 값이 아니다 — 요약으로 후보를 좁힌 뒤 **그 문서에만**
돌린다. 그 판단은 검색 도구가 한다(`services/harness/registry`).
"""

from .service import IntakeResult, intake_connector_documents, promote_to_searchable

__all__ = ["IntakeResult", "intake_connector_documents", "promote_to_searchable"]
