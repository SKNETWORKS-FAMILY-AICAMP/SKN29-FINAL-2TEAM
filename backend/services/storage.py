"""문서 저장소 — Drive에서 내려받은 원문을 보관한다.

지금은 로컬 디스크다. AWS 계정을 받으면 S3로 바뀌지만, 그때도 `doc.storage_key`
값은 그대로 쓸 수 있어야 한다. 그래서 키는 **경로가 아니라 저장소 안의 이름**으로
다룬다 — 호출자는 파일이 어디 있는지 모르고 키만 안다.

원문을 남기는 이유는 세 가지다.

- **Citation** — 추천 근거로 원문을 되짚어야 하는데, 원본이 없으면 못 보여준다.
- **재파싱** — 파서 설정을 바꿔 다시 돌릴 때마다 Drive를 때리면 토큰 만료·쿼터에
  걸린다. 한 번 받아 두면 그 뒤로는 로컬에서 반복할 수 있다.
- **변경 감지** — `content_hash`로 안 바뀐 문서를 다시 파싱하지 않는다.
"""

import hashlib
import os
from pathlib import Path

# 저장 위치. 기본값은 저장소 바깥이다 — `/app`은 소스 바인드 마운트라 여기에 쓰면
# 내려받은 문서가 git 작업 트리에 섞인다.
_DEFAULT_ROOT = "/var/lib/halil/documents"

# 확장자는 MIME에서 정한다. 원본 파일명을 경로에 쓰지 않는다 — 이름에 `/`나 `..`이
# 들어 있으면 저장소 밖으로 쓸 수 있고, Drive 파일명은 우리가 통제하지 못한다.
_EXTENSIONS = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
}


def storage_root() -> Path:
    return Path(os.environ.get("DOCUMENT_STORAGE_ROOT", _DEFAULT_ROOT))


def build_key(*, proj_id: str, doc_id: str, mime_type: str | None) -> str:
    """`doc.storage_key`에 넣을 값.

    프로젝트로 한 번 나눠 두면 한 프로젝트를 통째로 지울 때 디렉터리 하나만
    지우면 된다. 파일명은 `doc_id`라 중복도 덮어쓰기 사고도 없다.
    """

    return f"{proj_id}/{doc_id}{_EXTENSIONS.get(mime_type or '', '.bin')}"


def _resolved(key: str) -> Path:
    root = storage_root().resolve()
    path = (root / key).resolve()
    # 키는 우리가 만들지만, 저장소 밖을 가리키는 키가 들어오면 그 자체가 버그다.
    if not path.is_relative_to(root):
        raise ValueError(f"문서 저장소 밖을 가리키는 키입니다: {key}")
    return path


def save(key: str, data: bytes) -> str:
    """원문을 저장하고 `sha256:<hex>` 형태의 내용 해시를 돌려준다.

    같은 키로 다시 저장하면 덮어쓴다 — Drive에서 문서가 수정되면 새 내용이
    맞고, 이전 판은 `cur_revision`으로 구분한다.
    """

    path = _resolved(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    # 쓰다가 죽으면 반쪽짜리 파일이 남아 파싱이 그걸 읽는다. 임시 파일에 다 쓰고
    # 마지막에 이름을 바꿔 그 상태를 없앤다.
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(data)
    temporary.replace(path)
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def load(key: str) -> bytes:
    return _resolved(key).read_bytes()


def exists(key: str) -> bool:
    return _resolved(key).is_file()
