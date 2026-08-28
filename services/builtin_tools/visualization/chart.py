"""표·텍스트 값으로 Mermaid 차트 스펙을 만들어 SVG로 렌더한다.

이미지를 그리는 게 아니라 `pie`/`xychart-beta` **스펙 텍스트**를 만든 뒤
`render_mermaid`가 결정적으로 렌더한다.
"""

from __future__ import annotations

from typing import Any

from services.builtin_tools.common.errors import BuiltinToolError
from services.builtin_tools.visualization.renderer import CHART_PREFIXES, render_mermaid

MAX_CATEGORIES = 60
_CHART_TYPES = {"bar", "line", "pie"}


def _label(text: Any) -> str:
    cleaned = " ".join(str(text).replace('"', "'").split())
    return cleaned[:80] or "-"


def _number(text: Any) -> str:
    value = float(text)
    return str(int(value)) if value.is_integer() else f"{value:g}"


def build_chart(
    *,
    chart_type: str,
    title: str | None,
    labels: list[Any],
    values: list[Any],
) -> tuple[bytes, str]:
    """`(svg_bytes, mermaid_source)` 를 돌려준다."""

    kind = (chart_type or "bar").lower()
    if kind not in _CHART_TYPES:
        raise BuiltinToolError("UNSUPPORTED_CHART", "차트 종류는 bar, line, pie 중 하나여야 합니다.")
    if not labels or not values:
        raise BuiltinToolError("CHART_DATA_EMPTY", "차트에 넣을 라벨과 값이 필요합니다.")
    if len(labels) != len(values):
        raise BuiltinToolError(
            "CHART_DATA_MISMATCH", f"라벨 {len(labels)}개와 값 {len(values)}개가 서로 다릅니다."
        )
    if len(labels) > MAX_CATEGORIES:
        raise BuiltinToolError("TOO_MANY_CATEGORIES", f"항목은 {MAX_CATEGORIES}개까지입니다.")

    numbers: list[float] = []
    for value in values:
        try:
            numbers.append(float(value))
        except (TypeError, ValueError) as exc:
            raise BuiltinToolError(
                "NON_NUMERIC_VALUE", f"숫자가 아닌 값이 있습니다: {value!r}"
            ) from exc

    safe_labels = [_label(item) for item in labels]
    safe_title = _label(title) if title else "차트"

    if kind == "pie":
        if any(number < 0 for number in numbers):
            raise BuiltinToolError("NEGATIVE_PIE_VALUE", "파이 차트 값은 음수가 될 수 없습니다.")
        lines = [f"pie title {safe_title}"]
        lines += [f'    "{label}" : {_number(number)}' for label, number in zip(safe_labels, numbers)]
        code = "\n".join(lines)
    else:
        axis = "[" + ", ".join(f'"{label}"' for label in safe_labels) + "]"
        series = "[" + ", ".join(_number(number) for number in numbers) + "]"
        low = min(0.0, min(numbers))
        high = max(numbers)
        if high <= low:
            high = low + 1
        code = (
            "xychart-beta\n"
            f'    title "{safe_title}"\n'
            f"    x-axis {axis}\n"
            f'    y-axis "값" {_number(low)} --> {_number(high)}\n'
            f'    {"bar" if kind == "bar" else "line"} {series}'
        )

    return render_mermaid(code, allowed=CHART_PREFIXES), code
