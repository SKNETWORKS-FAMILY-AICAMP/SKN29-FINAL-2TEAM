"""Mermaid 스펙을 SVG로 렌더한다.

mermaid-cli가 요구하는 Node·headless Chrome 대신 mermaidx의 임베디드 QuickJS와
resvg를 쓴다 — 시스템 패키지가 없고 결과가 결정적이다. 래스터·AI 이미지가 아니라
텍스트 스펙에서 나온 벡터라 `document_convert`(→PDF)와 같은 포맷 변환이다.
"""

from __future__ import annotations

from services.builtin_tools.common.errors import BuiltinToolError

#: 스펙 길이 상한 — 모델이 만든 코드라 사람이 쓰는 것보다 넉넉히 둔다.
MAX_MERMAID_CHARS = 20_000

#: 다이어그램·그래프 도구가 허용하는 첫 키워드. 임의 Mermaid 지시문(스타일 주입,
#: `%%{init}%%` 등)이 화이트리스트를 우회하지 못하게 첫 비주석 토큰만 본다.
DIAGRAM_PREFIXES: frozenset[str] = frozenset(
    {
        "flowchart",
        "graph",
        "sequenceDiagram",
        "classDiagram",
        "erDiagram",
        "stateDiagram",
        "stateDiagram-v2",
        "gantt",
        "mindmap",
        "timeline",
        "journey",
        "requirementDiagram",
    }
)

#: 차트 도구가 허용하는 첫 키워드.
CHART_PREFIXES: frozenset[str] = frozenset({"pie", "xychart-beta"})


def _first_keyword(code: str) -> str:
    for line in code.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("%%"):
            continue
        head = stripped.split(None, 1)[0]
        # `pie title ...` 처럼 붙어 오는 경우와 `pie` 단독 모두 잡는다.
        return head.split("(", 1)[0]
    return ""


def render_mermaid(code: str, *, allowed: frozenset[str]) -> bytes:
    """검증된 Mermaid 코드를 SVG 바이트로 렌더한다.

    mermaidx는 임베디드 QuickJS 안에서 Mermaid 파서를 돌린다 — 그 자체가 JS
    샌드박스이고 결정적이라(POC 실측 ~50ms) 별도 프로세스로 감싸지 않는다.
    (`run_parser_isolated`의 spawn 은 매 호출 Python·Django·mermaidx 를 다시
    import 해서 6초가 넘었다.)
    """

    code = (code or "").strip()
    if not code:
        raise BuiltinToolError("EMPTY_SPEC", "그릴 내용이 비어 있습니다.")
    if len(code) > MAX_MERMAID_CHARS:
        raise BuiltinToolError(
            "SPEC_TOO_LARGE", f"스펙은 {MAX_MERMAID_CHARS:,}자 이하여야 합니다."
        )
    keyword = _first_keyword(code)
    if keyword not in allowed:
        raise BuiltinToolError(
            "UNSUPPORTED_DIAGRAM",
            f"지원하지 않는 종류입니다: {keyword or '(빈 값)'}. "
            f"허용: {', '.join(sorted(allowed))}",
        )

    import mermaidx

    try:
        svg = mermaidx.render(code, format="svg").svg(embed_font=True)
    except Exception as exc:  # noqa: BLE001 - QuickJS 파서 오류를 사용자용으로 정리한다.
        raise BuiltinToolError("MERMAID_SYNTAX", _friendly_error(exc)) from exc
    if not isinstance(svg, str) or "<svg" not in svg:
        raise BuiltinToolError("RENDER_FAILED", "SVG를 만들지 못했습니다.")
    return svg.encode("utf-8")


def _warm() -> None:
    """QuickJS에 Mermaid 번들을 미리 로드한다. **첫 렌더가 ~5초**라서, 워커가
    뜰 때 백그라운드로 한 번 돌려 두면 실제 사용자 요청은 ~50ms로 끝난다.
    실패해도 조용히 넘어간다 — 그때는 첫 실제 요청이 예열을 겸한다.
    """

    try:
        import mermaidx

        mermaidx.render("flowchart TD\n A --> B", format="svg").svg()
    except Exception:  # noqa: BLE001 - 예열 실패는 치명적이지 않다.
        pass


def _warm_in_background() -> None:
    import threading

    threading.Thread(target=_warm, name="mermaid-warm", daemon=True).start()


def _friendly_error(exc: Exception) -> str:
    """mermaidx 예외를 사용자에게 보여줄 한 줄로 정리한다.

    `RuntimeError: Mermaid rendering failed: Error: Parse error on line 3...` 처럼
    Mermaid 파서가 낸 문법 메시지는 경로가 없어 그대로 보여도 된다. 그 밖의
    엔진 내부 오류("Unknown quickjs tag" 등)는 감춘다.
    """

    raw = str(exc)
    marker = "Mermaid rendering failed:"
    if marker in raw:
        detail = raw.split(marker, 1)[1].replace("Error: ", "").strip()
        lowered = detail.lower()
        if detail and "quickjs" not in lowered and "traceback" not in lowered:
            first_line = detail.splitlines()[0]
            return f"Mermaid 문법 오류: {first_line[:200]}"
    return "Mermaid를 렌더하지 못했습니다. 문법을 확인해 주세요."
