"""시각화 Tool(diagram/chart/graph)의 렌더 계약.

Mermaid 스펙 → 결정적 SVG. 이미지 생성이 아니라 포맷 변환이라는 것을 고정한다.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from services.builtin_tools.common.errors import BuiltinToolError
from services.builtin_tools.visualization import build_chart, build_graph, render_mermaid
from services.builtin_tools.visualization.renderer import CHART_PREFIXES, DIAGRAM_PREFIXES


class DiagramRenderTests(SimpleTestCase):
    def test_korean_flowchart_renders_to_svg(self):
        svg = render_mermaid(
            "flowchart TD\n    A[사용자 질의] --> B{도구 필요?}\n"
            "    B -- 예 --> C[도구 실행]\n    B -- 아니오 --> D[바로 답변]",
            allowed=DIAGRAM_PREFIXES,
        )
        self.assertIn(b"<svg", svg)
        self.assertIn("사용자".encode(), svg)

    def test_supported_diagram_types_all_render(self):
        cases = {
            "sequence": "sequenceDiagram\n    participant U as 사용자\n    U->>S: 요청",
            "class": "classDiagram\n    Animal <|-- Dog\n    Animal : +String 이름",
            "er": "erDiagram\n    USER ||--o{ ORDER : places",
            "state": "stateDiagram-v2\n    [*] --> 대기\n    대기 --> 실행",
            "gantt": "gantt\n    title 일정\n    section A\n    작업 :a1, 2026-09-01, 3d",
            "mindmap": "mindmap\n  root((프로젝트))\n    설계\n    구현",
        }
        for name, code in cases.items():
            with self.subTest(diagram=name):
                self.assertIn(b"<svg", render_mermaid(code, allowed=DIAGRAM_PREFIXES))

    def test_non_whitelisted_first_keyword_is_rejected(self):
        # `%%{init}%%` 지시문으로 화이트리스트를 우회하려 해도 첫 비주석 토큰만 본다.
        with self.assertRaisesRegex(BuiltinToolError, "지원하지 않는 종류"):
            render_mermaid("%%{init: {}}%%\npie title x\n  \"a\" : 1", allowed=DIAGRAM_PREFIXES)

    def test_bad_syntax_gives_clean_error_without_internal_paths(self):
        with self.assertRaises(BuiltinToolError) as ctx:
            render_mermaid("flowchart TD\n    A --> ", allowed=DIAGRAM_PREFIXES)
        message = str(ctx.exception)
        self.assertNotIn("/app/", message)
        self.assertNotIn("Traceback", message)

    def test_oversized_spec_is_rejected(self):
        with self.assertRaisesRegex(BuiltinToolError, "이하"):
            render_mermaid("flowchart TD\n" + "A-->B\n" * 5000, allowed=DIAGRAM_PREFIXES)


class ChartBuildTests(SimpleTestCase):
    def test_bar_chart_from_labels_and_values(self):
        svg, code = build_chart(
            chart_type="bar",
            title="부서별 평균 공수",
            labels=["영업", "개발", "디자인"],
            values=[36, 41.33, 30],
        )
        self.assertIn(b"<svg", svg)
        self.assertTrue(code.startswith("xychart-beta"))
        self.assertIn("영업", code)

    def test_pie_chart(self):
        svg, code = build_chart(
            chart_type="pie", title="비율", labels=["A", "B", "C"], values=[2, 3, 1]
        )
        self.assertIn(b"<svg", svg)
        self.assertTrue(code.startswith("pie"))

    def test_rejects_mismatched_and_non_numeric(self):
        with self.assertRaisesRegex(BuiltinToolError, "서로 다릅니다"):
            build_chart(chart_type="bar", title=None, labels=["a", "b"], values=[1])
        with self.assertRaisesRegex(BuiltinToolError, "숫자가 아닌"):
            build_chart(chart_type="bar", title=None, labels=["a"], values=["x"])

    def test_pie_rejects_negative(self):
        with self.assertRaisesRegex(BuiltinToolError, "음수"):
            build_chart(chart_type="pie", title=None, labels=["a", "b"], values=[1, -2])

    def test_chart_spec_keyword_stays_in_whitelist(self):
        _svg, code = build_chart(
            chart_type="line", title="추이", labels=["1월", "2월"], values=[10, 20]
        )
        self.assertIn(code.split(None, 1)[0], CHART_PREFIXES)


class GraphBuildTests(SimpleTestCase):
    def test_nodes_and_edges_become_flowchart(self):
        svg, code = build_graph(
            nodes=[{"id": "api", "label": "API 서버"}, {"id": "db", "label": "PostgreSQL"}],
            edges=[{"from": "api", "to": "db", "label": "쿼리"}],
            direction="LR",
        )
        self.assertIn(b"<svg", svg)
        self.assertIn("flowchart LR", code)
        # 사용자 id 는 노출하지 않고 우리가 N0/N1 로 다시 붙인다.
        self.assertIn('N0["API 서버"]', code)
        self.assertIn("N0 -->|쿼리| N1", code)

    def test_edge_to_unknown_node_is_rejected(self):
        with self.assertRaisesRegex(BuiltinToolError, "없는 노드"):
            build_graph(
                nodes=[{"id": "a", "label": "A"}],
                edges=[{"from": "a", "to": "ghost"}],
                direction="TD",
            )

    def test_node_and_edge_caps(self):
        with self.assertRaisesRegex(BuiltinToolError, "노드는"):
            build_graph(
                nodes=[{"id": str(i)} for i in range(200)], edges=[], direction="TD"
            )


class DefaultChatToolsTests(SimpleTestCase):
    def test_visualization_tools_are_not_in_the_default_set(self):
        from services.harness.registry import ALWAYS_ON_TOOL_REFS, DEFAULT_CHAT_TOOL_REFS

        # 시각화 3종은 자주 안 써서 기본에서 뺐다(팀장이 Builder 에서 켠다).
        self.assertFalse(
            {"diagram_create", "chart_create", "graph_create"} & DEFAULT_CHAT_TOOL_REFS
        )
        # 시스템 도구는 별도 경로라 기본 집합에 없다.
        self.assertFalse(ALWAYS_ON_TOOL_REFS & DEFAULT_CHAT_TOOL_REFS)
        # 흔한 쓰기 도구는 기본이다(HITL 승인이 걸리므로).
        self.assertIn("table_export", DEFAULT_CHAT_TOOL_REFS)
        self.assertIn("document_convert", DEFAULT_CHAT_TOOL_REFS)

    def test_niche_tools_are_excluded_from_the_default_set(self):
        from services.harness.registry import BUILTIN_TOOLS, DEFAULT_CHAT_TOOL_REFS

        excluded = {
            "document_sync",
            "file_inspect",
            "file_sanitize",
            "archive_manage",
            "data_quality_check",
            "diagram_create",
            "chart_create",
            "graph_create",
            # 「업무 추출 에이전트」(prebuilt)가 담당한다 — 기본 어시스턴트는
            # 그 에이전트에 위임하지 직접 도구로 부르지 않는다(2026-08-30).
            "task_extraction",
        }
        self.assertFalse(excluded & DEFAULT_CHAT_TOOL_REFS)
        # 그 아홉만 빠진다 — 나머지는 전부 기본이다(시스템 2개 제외).
        self.assertEqual(len(DEFAULT_CHAT_TOOL_REFS), len(BUILTIN_TOOLS) - 2 - len(excluded))
        # 시연 범위라 남긴 것.
        self.assertIn("jira_get_issues", DEFAULT_CHAT_TOOL_REFS)
        # 도구 자체는 레지스트리에 그대로 있다(빌더에서 고를 수 있다).
        self.assertIn("task_extraction", BUILTIN_TOOLS)
