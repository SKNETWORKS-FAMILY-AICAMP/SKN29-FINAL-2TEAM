"""기존 Tool Registry(services/harness/registry.py)의 도구를 Deep Agents 호환
형식(tools/loader.py의 Tool)으로 변환한다.

⚠ 미구현. services/harness/registry.py의 BUILTIN_TOOLS 13종(document_search·
document_list·task_extraction·task_register·task_list·task_update·project_list·
workload_report·people_list·absence_list·web_search·jira_create_issues·
jira_get_issues, 2026-08-12 기준)을 하나씩 Tool(ref=..., injected_context=(...))로
감싸는 작업이다.

주의(02 §8.3): 지금 harness의 도구 핸들러들은 컨텍스트 인자를
inspect.signature()로 자동 추론해서 넘기는 경우가 있을 수 있다. 새 어댑터에서는
이 자동 추론을 쓰지 않고 injected_context를 각 도구마다 명시한다. 자동 추론이
남아있는 동안은 deprecation warning을 남기고, Deep Agent MVP 정식 배포 전에
자동 추론 fallback을 삭제한다.
"""

from __future__ import annotations


def adapt_builtin_tools() -> tuple:
    raise NotImplementedError(
        "services/harness/registry.py의 BUILTIN_TOOLS를 순회하며 tools.loader.Tool로 "
        "변환. 도구별 injected_context는 harness/runner.py의 현재 호출부를 근거로 정할 것."
    )
