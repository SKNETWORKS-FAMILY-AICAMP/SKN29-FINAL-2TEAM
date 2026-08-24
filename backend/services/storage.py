"""문서 저장소 — Drive에서 내려받은 원문과 사용자가 올린 파일을 보관한다.

**로컬 디스크와 S3 둘 다 된다**(2026-08-18). `OBJECT_STORAGE_PROVIDER` 가 고르고,
기본값은 `local` 이다. 키는 **경로가 아니라 저장소 안의 이름**이라 어느 쪽이든
`doc.storage_key` 값이 그대로 쓰인다 — 호출자는 파일이 어디 있는지 모르고 키만
안다. 그래서 이 파일 밖은 한 줄도 안 바뀐다.

**Django settings 를 안 읽는다.** 환경 변수를 직접 본다 — 이 모듈은 Django 밖
(스크립트·워커)에서도 import 되므로, settings 를 걸면 그쪽이 못 쓴다.

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


def build_personal_key(*, account_id: str, doc_id: str, mime_type: str | None) -> str:
    """개인이 올린 파일의 `doc.storage_key`.

    **팀 문서와 자리를 가른다**(2026-08-18 · 「내 파일」). `build_key` 는
    `{team_id}/` 로 시작하는데 개인 문서는 팀이 없어서 그 키가 `None/...` 이
    된다. 그리고 팀 아래에 두면 **팀을 통째로 지울 때 개인 파일이 함께
    지워진다** — 개인 소유로 둔 결정과 어긋난다.

    이름 있는 앞자리를 쓰는 것은 `avatar/` 와 같은 방식이다. 계정마다 디렉터리를
    하나 주는 것은, 계정을 지울 때 그 하나면 끝나게 하려는 것이다.
    """

    return f"user/{account_id}/{doc_id}{_EXTENSIONS.get(mime_type or '', '.bin')}"


#: 사용자가 올릴 수 있는 형식. **확장자에서 형식을 정한다** — 브라우저가 보내는
#: Content-Type 은 믿을 수 없고(아바타 업로드와 같은 판단), 문서는 바이트만으로
#: 형식을 못 가린다(아래 참조).
#:
#: **워커가 본문을 읽을 수 있는 것만 받는다** — `runpod_worker/pipeline.py` 의
#: `SUPPORTED_MIME_TYPES` 와 짝이다. 어긋나면 사용자는 올릴 수 있는데 색인만
#: 실패하는 파일을 갖게 된다(`tests/test_document_pipeline.py` 가 대조한다).
#:
#: txt·md 는 2026-08-24 에 워커가 읽게 됐다. 요약 단계를 없애면서 「워커는 못
#: 읽어도 요약은 우리 CPU 가 만든다」는 근거가 사라졌고, 그러면 이 둘이 올릴
#: 수만 있고 검색은 안 되는 형식이 되기 때문이다.
#:
#: pptx·xlsx 는 안 받는다. 워커가 못 읽는 것은 그대로다.
_UPLOAD_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
}

#: 앞부분 시그니처. 받는 둘 다 시그니처가 있어서 바이트로 한 번 더 본다.
_UPLOAD_SIGNATURES = {
    "application/pdf": b"%PDF-",
    # docx 는 zip 이다. 「zip 인가」까지만 확인할 수 있고 pptx·xlsx 와는 서로
    # 구분하지 못한다 — 그 둘은 받지 않으므로 지금은 문제가 되지 않는다.
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": b"PK",
}


def upload_mime_type(file_name: str, data: bytes) -> str | None:
    """올린 파일의 형식. 못 받는 것이면 `None`.

    **아바타만큼 강하지 않다.** 이미지는 시그니처로 형식이 갈리지만(`sniff_image_type`)
    문서는 그렇지 않다 — PDF 는 `%PDF-` 로 잡히는데 docx·pptx·xlsx 는 셋 다 zip 이라
    서로 구분되지 않고, txt·md·csv 는 시그니처가 아예 없다.

    그래서 **확장자 화이트리스트가 1차 관문**이고, 시그니처는 있는 것만 대조한다.
    이 차이를 적어 두지 않으면 다음 사람이 아바타를 보고 같은 수준으로 믿는다.
    확장자를 경로에 쓰지는 않는다 — 키는 `doc_id` 로 만든다.
    """

    _, dot, extension = file_name.rpartition(".")
    if not dot:
        return None
    mime = _UPLOAD_TYPES.get(f".{extension.lower()}")
    if mime is None:
        return None
    signature = _UPLOAD_SIGNATURES.get(mime)
    if signature and not data.startswith(signature):
        return None
    return mime


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


def _checked(key: str) -> str:
    """S3 용 키 검사.

    **경로 해석이 없다고 검사를 건너뛰지 않는다.** 로컬에서는 `_resolved` 가
    `..` 를 풀어 저장소 밖을 막는데, S3 는 키를 문자열로만 다뤄서 `a/../b` 가
    그대로 객체 이름이 된다 — 막히지는 않지만 **같은 파일이 두 이름으로 생긴다**
    (로컬에서는 하나였던 것이). 두 백엔드가 다르게 동작하면 갈아탈 때 드러난다.
    """

    if not key or key.startswith("/") or ".." in key.split("/"):
        raise ValueError(f"문서 저장소 밖을 가리키는 키입니다: {key}")
    return key


def _use_s3() -> bool:
    return os.environ.get("OBJECT_STORAGE_PROVIDER", "local").strip().lower() == "s3"


def _bucket() -> str:
    name = os.environ.get("AWS_STORAGE_BUCKET_NAME", "").strip()
    if not name:
        # 조용히 로컬로 떨어지지 않는다 — 저장은 됐는데 아무도 못 찾는 상태가
        # 되고, 그 사실이 파싱 실패로 한참 뒤에 드러난다.
        raise RuntimeError(
            "OBJECT_STORAGE_PROVIDER=s3 인데 AWS_STORAGE_BUCKET_NAME 이 비어 있습니다."
        )
    return name


def _client():
    """boto3 클라이언트. **키를 안 넘긴다** — 자격 증명은 boto3 가 찾는다.

    EC2 에서는 인스턴스 역할이, 로컬에서는 `AWS_ACCESS_KEY_ID`·
    `AWS_SECRET_ACCESS_KEY` 환경 변수가 잡힌다. 여기서 키를 읽어 넘기면 역할로
    도는 서버에서 빈 문자열을 자격 증명으로 넘기게 된다.
    """

    import boto3

    return boto3.client("s3", region_name=os.environ.get("AWS_S3_REGION_NAME") or None)


def content_hash(data: bytes) -> str:
    """`doc.content_hash` 에 넣는 값. `sha256:<hex>`.

    **저장하기 전에도 물을 수 있어야 한다**(2026-08-24). 변경 감지가 Drive 에서
    받은 바이트의 해시를 우리 기록과 대조한 뒤에야 저장할지 정하기 때문이다 —
    같으면 저장도 재색인도 하지 않는다.

    `save()` 도 이 함수를 쓴다. 계산식이 두 곳에 있으면 갈라지는 순간 **모든
    문서가 「바뀌었다」로 보여** 폴더를 저장할 때마다 전량 재파싱한다.
    """

    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def save(key: str, data: bytes) -> str:
    """원문을 저장하고 `sha256:<hex>` 형태의 내용 해시를 돌려준다.

    같은 키로 다시 저장하면 덮어쓴다 — Drive에서 문서가 수정되면 새 내용이
    맞고, 이전 판은 `cur_revision`으로 구분한다.
    """

    if _use_s3():
        _client().put_object(Bucket=_bucket(), Key=_checked(key), Body=data)
        # 반쪽 쓰기를 걱정하지 않는다 — S3 의 `PutObject` 는 원자적이라 성공하기
        # 전까지 이전 객체가 그대로 보인다(로컬의 `.part` → rename 과 같은 뜻).
        return content_hash(data)

    path = _resolved(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    # 쓰다가 죽으면 반쪽짜리 파일이 남아 파싱이 그걸 읽는다. 임시 파일에 다 쓰고
    # 마지막에 이름을 바꿔 그 상태를 없앤다.
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(data)
    temporary.replace(path)
    return content_hash(data)


def load(key: str) -> bytes:
    if _use_s3():
        return _client().get_object(Bucket=_bucket(), Key=_checked(key))["Body"].read()
    return _resolved(key).read_bytes()


def remove(key: str) -> None:
    """원문을 지운다. **이미 없으면 조용히 넘어간다.**

    부르는 쪽은 이미 DB 행을 지운 뒤다 — 여기서 「없다」로 터지면 화면은 삭제가
    실패했다고 말하는데 실제로는 끝난 상태가 된다.

    커넥터 문서에는 안 쓴다. 그쪽은 원본이 Drive 에 있어 사본을 남겨 두는 편이
    맞고(다시 받는 값이다), 이건 **원본이 우리뿐인 내 파일**을 위한 것이다.
    """

    if _use_s3():
        # S3 의 `DeleteObject` 는 없는 키에도 성공을 돌려준다 — 그 성질이 여기서
        # 필요한 동작과 같다.
        _client().delete_object(Bucket=_bucket(), Key=_checked(key))
        return
    _resolved(key).unlink(missing_ok=True)


def exists(key: str) -> bool:
    if _use_s3():
        from botocore.exceptions import ClientError

        try:
            _client().head_object(Bucket=_bucket(), Key=_checked(key))
        except ClientError as exc:
            # **없는 것과 못 읽는 것을 가른다.** 권한이 빠졌거나 버킷 이름이
            # 틀렸을 때 `False` 를 돌려주면 화면이 「원문 파일이 없습니다」라고
            # 말하고, 설정 문제를 아무도 못 본다.
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise
        return True
    return _resolved(key).is_file()
