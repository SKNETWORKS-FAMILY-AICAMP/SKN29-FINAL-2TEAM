"""외부 명령 없이 ZIP을 만들고 안전하게 해제한다."""

from __future__ import annotations

import stat
from io import BytesIO
from pathlib import PurePosixPath, PureWindowsPath
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo

from services.builtin_tools.common.errors import BuiltinToolError
from services.builtin_tools.common.limits import (
    MAX_ARCHIVE_FILES,
    MAX_ARCHIVE_RATIO,
    MAX_ARCHIVE_UNCOMPRESSED_BYTES,
    MAX_FILE_BYTES,
    MAX_OUTPUT_BYTES,
)


def _safe_entry_name(name: str) -> str:
    normalized = name.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(name)
    if (
        not normalized
        or "\x00" in normalized
        or normalized.startswith("/")
        or windows.is_absolute()
        or windows.drive
        or ".." in posix.parts
    ):
        raise BuiltinToolError("UNSAFE_ARCHIVE_PATH", "안전하지 않은 압축 파일 경로가 있습니다.")
    cleaned = "/".join(part for part in posix.parts if part not in ("", "."))
    if not cleaned:
        raise BuiltinToolError("UNSAFE_ARCHIVE_PATH", "비어 있는 압축 파일 경로가 있습니다.")
    return cleaned


def _is_symlink(info: ZipInfo) -> bool:
    return stat.S_ISLNK((info.external_attr >> 16) & 0xFFFF)


def create_zip(files: list[tuple[str, bytes]]) -> bytes:
    """이름과 바이트 목록을 하나의 ZIP 바이트로 만든다."""

    if not files:
        raise BuiltinToolError("EMPTY_ARCHIVE", "압축할 파일을 하나 이상 선택해 주세요.")
    if len(files) > MAX_ARCHIVE_FILES:
        raise BuiltinToolError("FILE_COUNT_EXCEEDED", "한 번에 500개 파일까지 압축할 수 있습니다.")
    names: set[str] = set()
    total = 0
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in files:
            safe_name = _safe_entry_name(name)
            if safe_name in names:
                raise BuiltinToolError("DUPLICATE_FILE_NAME", "압축할 파일 이름이 중복되었습니다.")
            names.add(safe_name)
            total += len(data)
            if total > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise BuiltinToolError("ARCHIVE_TOO_LARGE", "압축 전 전체 크기는 100MB 이하여야 합니다.")
            archive.writestr(safe_name, data)
    data = output.getvalue()
    if len(data) > MAX_OUTPUT_BYTES:
        raise BuiltinToolError("OUTPUT_TOO_LARGE", "결과 ZIP이 허용 크기를 초과했습니다.")
    return data


def extract_zip(data: bytes) -> list[tuple[str, bytes]]:
    """ZIP을 메모리에서 검사한 뒤 안전한 항목만 반환한다."""

    if not data:
        raise BuiltinToolError("EMPTY_FILE", "빈 ZIP 파일은 해제할 수 없습니다.")
    if len(data) > MAX_FILE_BYTES:
        raise BuiltinToolError("FILE_TOO_LARGE", "ZIP 파일은 20MB 이하여야 합니다.")
    try:
        archive = ZipFile(BytesIO(data))
        infos = archive.infolist()
    except BadZipFile as exc:
        raise BuiltinToolError("INVALID_ZIP", "손상되었거나 지원하지 않는 ZIP입니다.") from exc
    with archive:
        file_infos = [info for info in infos if not info.is_dir()]
        if len(file_infos) > MAX_ARCHIVE_FILES:
            raise BuiltinToolError("FILE_COUNT_EXCEEDED", "ZIP은 500개 파일까지 해제할 수 있습니다.")
        total = 0
        names: set[str] = set()
        checked: list[tuple[str, ZipInfo]] = []
        for info in file_infos:
            safe_name = _safe_entry_name(info.filename)
            if safe_name in names:
                raise BuiltinToolError("DUPLICATE_FILE_NAME", "ZIP 안에 중복된 파일 경로가 있습니다.")
            names.add(safe_name)
            if _is_symlink(info):
                raise BuiltinToolError(
                    "SYMLINK_NOT_ALLOWED", "심볼릭 링크가 포함된 ZIP은 해제할 수 없습니다."
                )
            if info.flag_bits & 0x1:
                raise BuiltinToolError("PASSWORD_REQUIRED", "암호가 설정된 ZIP은 해제할 수 없습니다.")
            total += info.file_size
            if total > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise BuiltinToolError("ARCHIVE_TOO_LARGE", "ZIP 해제 결과는 100MB 이하여야 합니다.")
            if info.file_size and info.compress_size == 0:
                raise BuiltinToolError(
                    "SUSPICIOUS_COMPRESSION", "비정상 압축률의 ZIP은 해제할 수 없습니다."
                )
            if info.compress_size and info.file_size / info.compress_size > MAX_ARCHIVE_RATIO:
                raise BuiltinToolError(
                    "SUSPICIOUS_COMPRESSION", "압축률이 지나치게 높은 ZIP은 해제할 수 없습니다."
                )
            checked.append((safe_name, info))
        try:
            return [(name, archive.read(info)) for name, info in checked]
        except (BadZipFile, RuntimeError) as exc:
            raise BuiltinToolError("INVALID_ZIP", "ZIP 내용을 끝까지 읽지 못했습니다.") from exc
