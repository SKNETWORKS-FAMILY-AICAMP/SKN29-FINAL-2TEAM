"""「내 파일」 API 표현."""

from typing import Any


def personal_file_response(row: dict[str, Any]) -> dict[str, Any]:
    """**상태를 하나로 뭉개지 않는다.** 사람이 할 행동이 각각 다르다 —

    - `extract_status` 가 없다 → 아직 읽는 중이다(기다린다)
    - `FAILED` → 텍스트를 못 뽑았다(다른 형식으로 다시 올린다)
    - `UNSUPPORTED` → 이 형식은 못 읽는다(포기한다)
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
        "uploaded_at": row.get("src_modified_at"),
    }
