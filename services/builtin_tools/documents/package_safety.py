"""OOXML(DOCX/XLSX) 압축 컨테이너를 parser 실행 전에 제한한다."""

from __future__ import annotations

import stat
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from services.builtin_tools.common.errors import BuiltinToolError
from services.builtin_tools.common.limits import (
    MAX_ARCHIVE_FILES,
    MAX_ARCHIVE_RATIO,
    MAX_ARCHIVE_UNCOMPRESSED_BYTES,
)


def validate_ooxml_package(data: bytes) -> None:
    """작은 입력이 parser 안에서 거대한 메모리로 팽창하는 것을 먼저 차단한다."""

    try:
        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_FILES:
                raise BuiltinToolError(
                    "TOO_MANY_ARCHIVE_FILES", "Office 문서 내부 파일이 너무 많습니다."
                )
            total_size = 0
            total_compressed = 0
            for info in entries:
                if stat.S_ISLNK((info.external_attr >> 16) & 0xFFFF):
                    raise BuiltinToolError(
                        "SYMLINK_NOT_ALLOWED", "Office 문서에 심볼릭 링크가 포함되어 있습니다."
                    )
                total_size += info.file_size
                total_compressed += info.compress_size
                if info.file_size and info.compress_size == 0:
                    raise BuiltinToolError(
                        "SUSPICIOUS_COMPRESSION", "Office 문서의 압축 구조가 비정상입니다."
                    )
                if info.compress_size and info.file_size / info.compress_size > MAX_ARCHIVE_RATIO:
                    raise BuiltinToolError(
                        "SUSPICIOUS_COMPRESSION", "Office 문서의 압축률이 안전 기준을 넘었습니다."
                    )
            if total_size > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise BuiltinToolError(
                    "ARCHIVE_TOO_LARGE", "Office 문서의 압축 해제 크기가 안전 기준을 넘었습니다."
                )
            if total_compressed and total_size / total_compressed > MAX_ARCHIVE_RATIO:
                raise BuiltinToolError(
                    "SUSPICIOUS_COMPRESSION", "Office 문서의 전체 압축률이 안전 기준을 넘었습니다."
                )
    except BadZipFile as exc:
        raise BuiltinToolError(
            "INVALID_OFFICE_FILE", "손상되었거나 지원하지 않는 Office 문서입니다."
        ) from exc


__all__ = ["validate_ooxml_package"]
