"""문서에 넣을 그림(SVG). 외부 파일 없이 PDF 안에 벡터로 들어간다.

**왜 필요한가** — 워커의 이미지 경로(`do_picture_description`·`do_chart_extraction`·
`do_picture_classification`)를 지금 세트가 하나도 건드리지 못한다. 100종이 전부
글자와 표뿐이라, 「그림이 든 문서를 파싱할 수 있는가」를 물을 수가 없다. 실제
개발 산업 문서에는 구성도·흐름도·추이 차트가 반드시 들어간다.

**왜 SVG 인가** — 파일을 따로 두지 않아도 되고, Chrome 이 그대로 PDF 벡터로
굽는다. 그리고 라벨이 `<text>` 로 들어가므로 **그림 속 글자가 파싱에 살아남는지**를
따로 잴 수 있다. 살아남지 않는다면 그것이 이 세트가 알아내려는 답 중 하나다.

라벨은 반드시 넣는다. 라벨 없는 도형은 파서에게 아무것도 묻지 못한다.
"""

from __future__ import annotations

import html

INK = "#111"
GRAY = "#888"
FILL = "#e9e9e9"


def _t(text: str) -> str:
    return html.escape(str(text))


def bar_chart(title: str, items: list[tuple[str, float]], *, unit: str = "", width: int = 560) -> str:
    """가로 막대 차트. `items` 는 (이름, 값)."""
    top, row_h, left = 34, 26, 150
    height = top + row_h * len(items) + 14
    peak = max(v for _, v in items) or 1
    bars = []
    for i, (label, value) in enumerate(items):
        y = top + i * row_h
        w = int((width - left - 90) * value / peak)
        bars.append(
            f'<text x="{left - 8}" y="{y + 13}" text-anchor="end" font-size="11">{_t(label)}</text>'
            f'<rect x="{left}" y="{y + 3}" width="{w}" height="14" fill="{FILL}" stroke="{INK}"/>'
            f'<text x="{left + w + 6}" y="{y + 14}" font-size="10.5">{_t(value)}{_t(unit)}</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" font-family="Malgun Gothic, sans-serif">'
        f'<text x="0" y="16" font-size="12.5" font-weight="700">{_t(title)}</text>'
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - 12}" stroke="{GRAY}"/>'
        + "".join(bars)
        + "</svg>"
    )


def flow(title: str, steps: list[str], *, width: int = 560) -> str:
    """좌에서 우로 흐르는 단계 도형. 단계가 5개를 넘으면 두 줄로 접는다."""
    per_row = 4 if len(steps) > 4 else len(steps)
    rows = [steps[i : i + per_row] for i in range(0, len(steps), per_row)]
    box_w, box_h, gap, top = (width - 40) // per_row - 14, 42, 14, 34
    height = top + len(rows) * (box_h + 26)
    parts = [f'<text x="0" y="16" font-size="12.5" font-weight="700">{_t(title)}</text>']
    for r, row in enumerate(rows):
        y = top + r * (box_h + 26)
        for c, step in enumerate(row):
            x = c * (box_w + gap)
            parts.append(
                f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="3" '
                f'fill="#fff" stroke="{INK}"/>'
                f'<text x="{x + box_w // 2}" y="{y + box_h // 2 + 4}" text-anchor="middle" '
                f'font-size="10.5">{_t(step)}</text>'
            )
            if c < len(row) - 1:
                mid = y + box_h // 2
                parts.append(
                    f'<line x1="{x + box_w}" y1="{mid}" x2="{x + box_w + gap}" y2="{mid}" '
                    f'stroke="{INK}"/>'
                    f'<polygon points="{x + box_w + gap},{mid} {x + box_w + gap - 5},{mid - 3} '
                    f'{x + box_w + gap - 5},{mid + 3}" fill="{INK}"/>'
                )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" font-family="Malgun Gothic, sans-serif">'
        + "".join(parts)
        + "</svg>"
    )


def stack(title: str, layers: list[tuple[str, str]], *, width: int = 560) -> str:
    """위에서 아래로 쌓은 계층 구성도. `layers` 는 (계층 이름, 그 안의 요소)."""
    top, row_h = 34, 46
    height = top + row_h * len(layers) + 6
    parts = [f'<text x="0" y="16" font-size="12.5" font-weight="700">{_t(title)}</text>']
    for i, (name, inner) in enumerate(layers):
        y = top + i * row_h
        parts.append(
            f'<rect x="0" y="{y}" width="{width}" height="{row_h - 8}" fill="{FILL}" stroke="{INK}"/>'
            f'<text x="10" y="{y + 16}" font-size="11" font-weight="700">{_t(name)}</text>'
            f'<text x="10" y="{y + 30}" font-size="10">{_t(inner)}</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" font-family="Malgun Gothic, sans-serif">'
        + "".join(parts)
        + "</svg>"
    )


def gantt(title: str, rows: list[tuple[str, int, int]], *, months: list[str], width: int = 560) -> str:
    """간단한 일정 막대. `rows` 는 (과업, 시작 칸, 칸 수)."""
    left, top, row_h = 130, 46, 22
    span = (width - left) // max(len(months), 1)
    height = top + row_h * len(rows) + 10
    parts = [f'<text x="0" y="16" font-size="12.5" font-weight="700">{_t(title)}</text>']
    for i, label in enumerate(months):
        parts.append(
            f'<text x="{left + i * span + span // 2}" y="{top - 6}" text-anchor="middle" '
            f'font-size="9.5">{_t(label)}</text>'
            f'<line x1="{left + i * span}" y1="{top}" x2="{left + i * span}" y2="{height - 8}" '
            f'stroke="#ddd"/>'
        )
    for i, (label, start, length) in enumerate(rows):
        y = top + i * row_h
        parts.append(
            f'<text x="{left - 8}" y="{y + 14}" text-anchor="end" font-size="10">{_t(label)}</text>'
            f'<rect x="{left + start * span}" y="{y + 4}" width="{length * span}" height="12" '
            f'fill="{FILL}" stroke="{INK}"/>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" font-family="Malgun Gothic, sans-serif">'
        + "".join(parts)
        + "</svg>"
    )
