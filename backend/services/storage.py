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


def build_key(*, team_id: str, doc_id: str, mime_type: str | None) -> str:
    """`doc.storage_key`에 넣을 값.

    팀으로 한 번 나눠 두면 한 팀을 통째로 지울 때 디렉터리 하나만 지우면 된다.
    파일명은 `doc_id`라 중복도 덮어쓰기 사고도 없다.

    프로젝트가 아니라 팀으로 나눈다(2026-08-04) — 문서는 등록 시점에 어느
    프로젝트 것인지 모르고, 나중에 지정된다고 파일을 옮길 수는 없다.
    """

    return f"{team_id}/{doc_id}{_EXTENSIONS.get(mime_type or '', '.bin')}"


# 프로필 사진으로 받을 형식. 확장자는 여기서 정한다 — 업로드된 파일명을 경로에
# 쓰면 `..`이나 `/`로 저장소 밖을 가리킬 수 있다.
AVATAR_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

# 파일 앞부분의 시그니처. Content-Type 은 보내는 쪽이 정하는 값이라 믿을 수 없다 —
# 실제로 이미지인지는 바이트를 봐야 안다.
_IMAGE_SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)


def sniff_image_type(data: bytes) -> str | None:
    """실제 바이트로 판정한 이미지 형식. 모르면 `None`.

    WebP 는 `RIFF....WEBP` 구조라 앞 4바이트만으로는 구분되지 않아 따로 본다.
    """

    for signature, mime in _IMAGE_SIGNATURES:
        if data.startswith(signature):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def build_avatar_key(*, account_id: str, mime_type: str) -> str:
    """`user_account.avatar_key`에 넣을 값.

    계정마다 한 장이라 파일명이 `account_id`다. 새로 올리면 같은 키를 덮어써서
    옛 사진이 저장소에 남지 않는다.
    """

    return f"avatar/{account_id}{AVATAR_TYPES[mime_type]}"


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
