"""고정된 문서 변환 실행 파일을 timeout과 격리 환경으로 실행한다."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
from pathlib import Path

from services.builtin_tools.common.errors import BuiltinToolError

_MAX_DIAGNOSTIC_BYTES = 4096
_ALLOWED_EXECUTABLES = frozenset({"exiftool", "pandoc", "soffice"})


def run_command(
    executable: str,
    arguments: list[str],
    *,
    cwd: Path,
    home: Path,
    timeout_seconds: int,
    input_data: bytes | None = None,
) -> tuple[bytes, bytes]:
    """Shell 없이 설치된 실행 파일 하나를 제한된 환경에서 실행한다."""

    if executable not in _ALLOWED_EXECUTABLES:
        raise BuiltinToolError("EXECUTABLE_NOT_ALLOWED", "허용되지 않은 문서 처리 명령입니다.")
    resolved = shutil.which(executable)
    if resolved is None:
        raise BuiltinToolError(
            "DEPENDENCY_UNAVAILABLE", "문서 처리 구성 요소가 설치되어 있지 않습니다."
        )
    environment = {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "SAL_USE_VCLPLUGIN": "svp",
    }
    try:
        process = subprocess.Popen(  # noqa: S603 - executable과 인자는 코드에서 고정한다.
            [resolved, *arguments],
            cwd=cwd,
            env=environment,
            stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(input=input_data, timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise BuiltinToolError(
                "PROCESS_TIMEOUT", "문서 처리가 제한 시간 안에 끝나지 않았습니다."
            ) from exc
    except OSError as exc:
        raise BuiltinToolError("PROCESS_START_FAILED", "문서 처리를 시작하지 못했습니다.") from exc
    if process.returncode != 0:
        # stderr는 파일 경로나 원문을 포함할 수 있어 사용자 오류에는 넣지 않는다.
        _ = stderr[-_MAX_DIAGNOSTIC_BYTES:]
        raise BuiltinToolError("PROCESS_FAILED", "문서 처리 구성 요소가 작업을 완료하지 못했습니다.")
    return stdout, stderr[-_MAX_DIAGNOSTIC_BYTES:]
