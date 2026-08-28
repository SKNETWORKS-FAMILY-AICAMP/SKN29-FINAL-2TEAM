"""신뢰하지 않는 문서 parser를 제한된 별도 프로세스에서 실행한다."""

from __future__ import annotations

import importlib
import multiprocessing
import sys
from typing import Any

from services.builtin_tools.common.errors import BuiltinToolError

PARSER_TIMEOUT_SECONDS = 45
PARSER_MEMORY_BYTES = 768 * 1024 * 1024
PARSER_CPU_SECONDS = 30


def _child(connection, module_name: str, function_name: str, kwargs: dict[str, Any]) -> None:
    try:
        if sys.platform.startswith("linux"):
            import resource

            resource.setrlimit(resource.RLIMIT_AS, (PARSER_MEMORY_BYTES, PARSER_MEMORY_BYTES))
            resource.setrlimit(resource.RLIMIT_CPU, (PARSER_CPU_SECONDS, PARSER_CPU_SECONDS))
        function = getattr(importlib.import_module(module_name), function_name)
        connection.send(("OK", function(**kwargs)))
    except BuiltinToolError as exc:
        connection.send(("TOOL_ERROR", exc.code, exc.message))
    except BaseException:  # noqa: BLE001 - parser 원문·경로·내부 오류는 부모로 보내지 않는다.
        connection.send(("PARSER_ERROR",))
    finally:
        connection.close()


def run_parser_isolated(
    *, module_name: str, function_name: str, kwargs: dict[str, Any]
) -> Any:
    """parser 결과만 반환하고 timeout·crash·메모리 초과를 안정적인 오류로 바꾼다."""
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(
        target=_child,
        args=(child, module_name, function_name, kwargs),
        daemon=True,
    )
    process.start()
    child.close()
    try:
        if not parent.poll(PARSER_TIMEOUT_SECONDS):
            process.terminate()
            process.join(timeout=2)
            if process.is_alive():
                process.kill()
                process.join(timeout=2)
            raise BuiltinToolError("PARSER_TIMEOUT", "문서 처리 시간이 제한을 초과했습니다.")
        payload = parent.recv()
    except EOFError as exc:
        raise BuiltinToolError("PARSER_FAILED", "문서 처리 프로세스가 종료되었습니다.") from exc
    finally:
        parent.close()
        if process.is_alive():
            process.join(timeout=2)
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)

    if payload[0] == "OK":
        return payload[1]
    if payload[0] == "TOOL_ERROR":
        raise BuiltinToolError(payload[1], payload[2])
    raise BuiltinToolError("PARSER_FAILED", "문서 내용을 안전하게 처리하지 못했습니다.")
