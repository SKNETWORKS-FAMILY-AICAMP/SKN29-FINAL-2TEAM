"""문서 명세(dict) → HTML. 조판만 맡고 내용은 명세가 가진다.

90여 종을 손으로 HTML 을 쓰면 시간도 시간이지만 **문서 모양이 균일해진다.**
모양이 같으면 임베딩 공간에서 서로 가까워져 노이즈가 노이즈 구실을 못 한다.
그래서 절 유형을 여러 개 두고 문서마다 다르게 섞는다.

절 유형:
    ("h2", "제목")                      큰 제목
    ("h3", "제목")                      작은 제목
    ("p", "문단")                       서술
    ("ul", ["항목", ...])               목록
    ("table", [머리행], [[칸, ...]])     표
    ("kv", [("이름", "값"), ...])        2열 표(표지·요약용)
    ("note", "문단")                    강조 상자
    ("break", None)                     쪽 나눔
    ("figure", (svg, "그림 설명"))       SVG 그림. `figures.py` 가 만든다

문서는 `style` 로 서식을 고를 수 있다(`doc.css`·`gov.css`·`report.css`·`memo.css`).
안 주면 `doc.css` 다. **서식을 여러 벌 두는 이유는 파싱 평가 때문이다** — 모든
문서가 같은 서식이면 제목 인식이 나쁠 때 그것이 파서 탓인지 서식 탓인지 가를 수 없다.
"""

from __future__ import annotations

import html
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _esc(text) -> str:
    return html.escape(str(text))


def _row(cells, tag="td") -> str:
    return "<tr>" + "".join(f"<{tag}>{_esc(c)}</{tag}>" for c in cells) + "</tr>"


def _section(kind, value) -> str:
    if kind in ("h2", "h3", "h4"):
        return f"<{kind}>{_esc(value)}</{kind}>"
    if kind == "p":
        return f"<p>{_esc(value)}</p>"
    if kind == "note":
        return f'<div class="note">{_esc(value)}</div>'
    if kind == "ul":
        return "<ul>" + "".join(f"<li>{_esc(v)}</li>" for v in value) + "</ul>"
    if kind == "kv":
        rows = "".join(f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in value)
        return f'<table class="cover-meta">{rows}</table>'
    if kind == "table":
        head, body = value
        return (
            "<table>"
            + _row(head, "th")
            + "".join(_row(r) for r in body)
            + "</table>"
        )
    if kind == "break":
        return '<div class="pagebreak"></div>'
    if kind == "figure":
        svg, caption = value
        # SVG 를 그대로 넣는다. 라벨이 `<text>` 라 **그림 속 글자가 파싱에 살아남는지**
        # 따로 잴 수 있다. 살아남지 않는다면 그것도 알아내려는 답 중 하나다.
        return f'<figure>{svg}<figcaption>{_esc(caption)}</figcaption></figure>'
    raise ValueError(f"모르는 절 유형: {kind}")


def render(spec: dict) -> str:
    """`{title, sections}` 을 완성된 HTML 문서로."""
    body = "\n".join(_section(kind, value) for kind, value in spec["sections"])
    title = _esc(spec["title"])
    style = _esc(spec.get("style", "doc.css"))
    heading = title.replace(" — ", "<br>")
    return (
        "<!doctype html>\n<html lang=\"ko\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{title}</title>\n"
        f'<link rel="stylesheet" href="{style}">\n</head>\n<body>\n'
        f"<h1>{heading}</h1>\n{body}\n</body>\n</html>\n"
    )


def write(spec: dict, *, out_dir: Path | None = None) -> Path:
    path = (out_dir or HERE) / spec["source"]
    path.write_text(render(spec), encoding="utf-8")
    return path
