"""「내 파일」 API 표현."""

from typing import Any


def personal_file_response(row: dict[str, Any]) -> dict[str, Any]:
    """**상태를 하나로 뭉개지 않는다.** 사람이 할 행동이 각각 다르다 —

    - `extract_status` 가 없다 → 아직 읽는 중이다(기다린다)
    - `FAILED` → 텍스트를 못 뽑았다(다른 형식으로 다시 올린다)
    - `UNSUPPORTED` → 이 형식은 못 읽는다(포기한다)

    실패한 둘은 `extract_detail` 로 **이유까지** 준다 — 「암호가 걸린 PDF 라
    열 수 없습니다」와 「텍스트 레이어가 없는 PDF 입니다(스캔본으로
    보입니다)」는 사람이 할 행동이 정반대다(2026-08-19).
    - `search_ready` → 본문까지 색인됐다(할 일 없음)

    하나로 합치면 「안 됨」만 남고, 그중 무엇인지 알 수 없다.
    """

    return {
        "doc_id": row["doc_id"],
        "file_name": row["file_name"],
        "mime_type": row["mime_type"],
        "search_enabled": row["search_enabled"],
        "search_ready": row["search_ready"],
        "summary": row.get("summary"),
        "doc_type": row.get("doc_type"),
        "keywords": row.get("keywords") or [],
        "extract_status": row.get("extract_status"),
        # **왜 실패했는지.** 상태만으로는 사람이 할 행동이 안 정해진다 —
        # 「암호가 걸린 PDF」면 암호를 풀어 다시 올리면 되고, 「스캔본」이면
        # 다시 올려도 같다. OK 인 문서는 비어 있다(2026-08-19).
        "extract_detail": row.get("extract_detail"),
        # 청크 파싱·임베딩 단계. RUNNING / FAILED / null(안 돌렸거나 끝남).
        # `extract_status` 와 다른 단계다 — 둘은 따로 실패한다.
        "index_status": row.get("index_status"),
        "uploaded_at": row.get("src_modified_at"),
        "shared": row.get("shared_team_id") is not None,
        # 공유 받은 목록에만 있다. 누가 올렸는지 모르면 내용을 믿을 근거가 없다.
        "owner_name": row.get("owner_name"),
    }
