"""「내 파일」 API 표현."""

from typing import Any


def personal_file_response(row: dict[str, Any]) -> dict[str, Any]:
    """**상태를 하나로 뭉개지 않는다.** 사람이 할 행동이 각각 다르다 —

    - `index_status` 가 없고 `search_ready` 도 false → 아직 차례가 안 왔다(기다린다)
    - `RUNNING` → 읽는 중이다(기다린다)
    - `FAILED` → 못 읽었다. `index_detail` 이 **왜인지** 말한다
    - `search_ready` → 본문까지 색인됐다(할 일 없음)

    하나로 합치면 「안 됨」만 남고, 그중 무엇인지 알 수 없다.

    2026-08-24 에 요약 단계를 없애면서 `extract_status`·`extract_detail` 이
    사라지고 색인 단계의 `index_status`·`index_detail` 이 그 역할을 이어받았다 —
    묻는 것이 「요약이 됐나」에서 「본문이 색인됐나」로 바뀌었기 때문이다.
    """

    return {
        "doc_id": row["doc_id"],
        "file_name": row["file_name"],
        "mime_type": row["mime_type"],
        "search_enabled": row["search_enabled"],
        "search_ready": row["search_ready"],
        # 청크 파싱·임베딩 단계. RUNNING / FAILED / null(안 돌렸거나 끝남).
        "index_status": row.get("index_status"),
        # **왜 실패했는지.** 상태만으로는 사람이 할 행동이 안 정해진다 —
        # 「암호가 걸린 PDF」면 암호를 풀어 다시 올리면 되고, 「스캔본」이면
        # 다시 올려도 같다. 성공한 문서는 비어 있다.
        "index_detail": row.get("index_detail"),
        "uploaded_at": row.get("src_modified_at"),
        "shared": row.get("shared_team_id") is not None,
        # 공유 받은 목록에만 있다. 누가 올렸는지 모르면 내용을 믿을 근거가 없다.
        "owner_name": row.get("owner_name"),
    }
