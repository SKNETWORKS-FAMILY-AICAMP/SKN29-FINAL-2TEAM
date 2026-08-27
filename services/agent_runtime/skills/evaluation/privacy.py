"""회귀 평가 데이터가 원문·식별정보를 다시 영구 저장하지 않게 검사한다."""

from __future__ import annotations

import json
import re
from typing import Any

from django.conf import settings


class RegressionPrivacyError(ValueError):
    pass


_SENSITIVE_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9_.+-])[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9_-])"),
    re.compile(r"(?<!\d)(?:\d[ -]?){9,}\d(?!\d)"),
    re.compile(r"(?<![A-Za-z0-9])(?:sk|pk|api|token|secret)[-_][A-Za-z0-9_-]{8,}(?![A-Za-z0-9_-])", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9])(?:UA|AC|TM|TE|AG|AV|DC|DOC)\d{3,}(?![A-Za-z0-9])"),
)


def validate_anonymized_case(document: dict[str, Any]) -> None:
    """익명화는 운영자가 수행하고, 코드는 명백한 누출과 형식 오류를 차단한다."""

    messages = document.get("messages")
    if not isinstance(messages, list) or not messages:
        raise RegressionPrivacyError("익명화된 메시지가 한 개 이상 필요합니다.")
    if len(messages) > settings.SKILL_EVAL_REGRESSION_CASE_MAX_MESSAGES:
        raise RegressionPrivacyError("회귀 사례의 대화가 허용된 개수를 넘었습니다.")
    if document.get("polarity") not in {"positive", "negative"}:
        raise RegressionPrivacyError("평가 기대값의 종류가 올바르지 않습니다.")
    serialized = json.dumps(document, ensure_ascii=False, sort_keys=True)
    if len(serialized.encode("utf-8")) > settings.SKILL_EVAL_REGRESSION_CASE_MAX_BYTES:
        raise RegressionPrivacyError("회귀 사례가 허용된 크기를 넘었습니다.")
    if any(pattern.search(serialized) for pattern in _SENSITIVE_PATTERNS):
        raise RegressionPrivacyError("익명화되지 않은 식별정보 형식이 남아 있습니다.")

    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in {"user", "assistant"}:
            raise RegressionPrivacyError("메시지 역할과 내용 형식이 올바르지 않습니다.")
        if not isinstance(message.get("content"), str) or not message["content"].strip():
            raise RegressionPrivacyError("빈 메시지는 회귀 사례로 등록할 수 없습니다.")


def validate_regression_case_shape(document: dict[str, Any]) -> None:
    """승인된 사례가 ``SkillEvalCase``로 실제 실행 가능한지 검사한다."""

    validate_anonymized_case(document)
    if not isinstance(document.get("category"), str) or not document["category"].strip():
        raise RegressionPrivacyError("회귀 사례의 분류가 필요합니다.")
    if not isinstance(document.get("should_activate_candidate"), bool):
        raise RegressionPrivacyError("스킬 사용 기대값이 올바르지 않습니다.")
    if document["should_activate_candidate"] != (document["polarity"] == "positive"):
        raise RegressionPrivacyError("긍정·부정 구분과 스킬 사용 기대값이 일치하지 않습니다.")
    if not isinstance(document.get("tool_fixtures"), dict):
        raise RegressionPrivacyError("도구 준비 데이터 형식이 올바르지 않습니다.")
    if any(not isinstance(key, str) or not isinstance(value, list) for key, value in document["tool_fixtures"].items()):
        raise RegressionPrivacyError("도구 준비 데이터 형식이 올바르지 않습니다.")
    for field in (
        "document_fixtures", "allowed_other_skill_names", "required_tools",
        "forbidden_tools", "approval_fixtures", "behavior_assertions",
    ):
        if not isinstance(document.get(field), list):
            raise RegressionPrivacyError("회귀 사례의 기대값 목록 형식이 올바르지 않습니다.")
    if any(not isinstance(name, str) or not name for name in document["allowed_other_skill_names"]):
        raise RegressionPrivacyError("허용할 다른 스킬 이름 형식이 올바르지 않습니다.")
    if any(not isinstance(name, str) or not name for name in document["forbidden_tools"]):
        raise RegressionPrivacyError("금지 도구 형식이 올바르지 않습니다.")
    for expectation in document["required_tools"]:
        if not isinstance(expectation, dict) or not isinstance(expectation.get("tool_ref"), str):
            raise RegressionPrivacyError("필수 도구 기대값 형식이 올바르지 않습니다.")
        if not isinstance(expectation.get("min_calls", 1), int):
            raise RegressionPrivacyError("필수 도구 호출 횟수 형식이 올바르지 않습니다.")
        if expectation.get("min_calls", 1) < 0:
            raise RegressionPrivacyError("필수 도구 최소 호출 횟수는 음수일 수 없습니다.")
        max_calls = expectation.get("max_calls")
        if max_calls is not None and not isinstance(max_calls, int):
            raise RegressionPrivacyError("필수 도구 최대 호출 횟수 형식이 올바르지 않습니다.")
        if max_calls is not None and max_calls < expectation.get("min_calls", 1):
            raise RegressionPrivacyError("필수 도구 최대 호출 횟수가 최소 횟수보다 작습니다.")
        if not isinstance(expectation.get("argument_rules", []), list):
            raise RegressionPrivacyError("필수 도구 인자 검사 형식이 올바르지 않습니다.")
    for fixture in document["document_fixtures"]:
        if not isinstance(fixture, dict) or any(
            not isinstance(fixture.get(key), str) or not fixture[key]
            for key in ("document_id", "title", "content")
        ):
            raise RegressionPrivacyError("문서 준비 데이터 형식이 올바르지 않습니다.")
        if not isinstance(fixture.get("indexed"), bool):
            raise RegressionPrivacyError("문서 색인 상태 형식이 올바르지 않습니다.")
    for fixture in document["approval_fixtures"]:
        if (
            not isinstance(fixture, dict)
            or not isinstance(fixture.get("tool_ref"), str)
            or fixture.get("decision") not in {"approve", "reject"}
        ):
            raise RegressionPrivacyError("승인 준비 데이터 형식이 올바르지 않습니다.")
    if any(not isinstance(item, dict) for item in document["behavior_assertions"]):
        raise RegressionPrivacyError("결과 검사 기준 형식이 올바르지 않습니다.")


__all__ = ["RegressionPrivacyError", "validate_anonymized_case", "validate_regression_case_shape"]
