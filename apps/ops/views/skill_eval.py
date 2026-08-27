"""운영자가 신고를 익명 회귀 사례로 전환하고 승인하는 API."""

from __future__ import annotations

from datetime import date, datetime
import logging
from uuid import UUID, uuid4

import psycopg
from django.conf import settings
from rest_framework.response import Response

from backend.db.skill_eval import (
    SkillEvalFeedbackNotFound,
    SkillEvalFeedbackRepository,
    SkillEvalRegressionCaseNotFound,
    SkillEvalRegressionCaseRepository,
)
from services.agent_runtime.skills.evaluation.privacy import (
    RegressionPrivacyError,
    validate_regression_case_shape,
)
from services.agent_runtime.skills.service import validate_skill_name

from ..authentication import AdminView

logger = logging.getLogger(__name__)


class SkillEvalAdminView(AdminView):
    def handle_exception(self, exc):
        if isinstance(exc, psycopg.Error):
            logger.exception("스킬 평가 운영 API의 데이터베이스 요청 실패")
            return Response({"detail": "평가 데이터를 처리하지 못했습니다. 잠시 후 다시 시도해 주세요."}, status=503)
        return super().handle_exception(exc)


def _json_value(value):
    if isinstance(value, (UUID, datetime, date)):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _validate_status(value: str | None, allowed: set[str]):
    if value is not None and value not in allowed:
        return Response({"detail": "상태 값이 올바르지 않습니다."}, status=400)
    return None


def _dataset_version(data) -> str:
    value = str(data.get("dataset_version") or "v1").strip()
    if not value or len(value) > settings.SKILL_EVAL_DATASET_VERSION_MAX_LENGTH:
        raise ValueError("평가 데이터 버전 형식이 올바르지 않습니다.")
    return value


def _case_payload(data):
    scope = str(data.get("scope") or "").upper()
    polarity = str(data.get("polarity") or "").lower()
    team_id = str(data.get("team_id") or "").strip() or None
    skill_name = str(data.get("skill_name") or "").strip() or None
    tags = data.get("capability_tags") or []
    document = data.get("case_document")
    if scope not in {"GLOBAL", "TEAM", "SKILL"}:
        raise ValueError("회귀 사례의 적용 범위가 올바르지 않습니다.")
    if polarity not in {"positive", "negative"}:
        raise ValueError("평가 기대값이 올바르지 않습니다.")
    if scope == "TEAM" and not team_id:
        raise ValueError("팀 범위 사례에는 팀 정보가 필요합니다.")
    if scope == "SKILL" and not skill_name:
        raise ValueError("스킬 범위 사례에는 스킬 이름이 필요합니다.")
    if scope == "GLOBAL":
        team_id = None
        skill_name = None
    elif scope == "TEAM":
        skill_name = None
    if skill_name:
        error = validate_skill_name(skill_name, allow_reserved=True)
        if error:
            raise ValueError(error)
    if not isinstance(tags, list) or any(not isinstance(tag, str) or not tag.strip() for tag in tags):
        raise ValueError("기능 분류 값의 형식이 올바르지 않습니다.")
    tags = list(dict.fromkeys(tag.strip() for tag in tags))
    if len(tags) > settings.SKILL_EVAL_MAX_CAPABILITY_TAGS or any(
        len(tag) > settings.SKILL_EVAL_CAPABILITY_TAG_MAX_LENGTH for tag in tags
    ):
        raise ValueError("기능 분류가 허용된 개수나 길이를 넘었습니다.")
    if not isinstance(document, dict):
        raise ValueError("익명화한 테스트 내용이 필요합니다.")
    document = {
        "category": str(document.get("category") or "regression"),
        "messages": document.get("messages"),
        "document_fixtures": [
            {**fixture, "indexed": bool(fixture.get("indexed", True))}
            if isinstance(fixture, dict) else fixture
            for fixture in (document.get("document_fixtures") or [])
        ],
        "tool_fixtures": document.get("tool_fixtures") or {},
        "should_activate_candidate": polarity == "positive",
        "allowed_other_skill_names": document.get("allowed_other_skill_names") or [],
        "required_tools": document.get("required_tools") or [],
        "forbidden_tools": document.get("forbidden_tools") or [],
        "approval_fixtures": document.get("approval_fixtures") or [],
        "behavior_assertions": document.get("behavior_assertions") or [],
        "reason": str(document.get("reason") or ""),
        "polarity": polarity,
    }
    list_fields = (
        "document_fixtures", "allowed_other_skill_names", "required_tools",
        "forbidden_tools", "approval_fixtures", "behavior_assertions",
    )
    if any(not isinstance(document[field], list) for field in list_fields) or not isinstance(document["tool_fixtures"], dict):
        raise ValueError("테스트 기대값과 준비 데이터의 형식이 올바르지 않습니다.")
    validate_regression_case_shape(document)
    return scope, team_id, skill_name, tags, polarity, document


class SkillEvalFeedbackListView(SkillEvalAdminView):
    def get(self, request):
        review_status = request.query_params.get("status")
        error = _validate_status(review_status, {"PENDING", "CONVERTED", "DISMISSED"})
        if error:
            return error
        rows = SkillEvalFeedbackRepository.list_for_review(status=review_status)
        return Response({"items": _json_value(rows)})


class SkillEvalFeedbackDetailView(SkillEvalAdminView):
    def patch(self, request, feedback_id):
        if request.data.get("action") != "dismiss":
            return Response({"detail": "지원하지 않는 처리입니다."}, status=400)
        try:
            row = SkillEvalFeedbackRepository.dismiss(feedback_id, reviewed_by=request.user.account_id)
        except SkillEvalFeedbackNotFound as exc:
            return Response({"detail": str(exc)}, status=404)
        return Response(_json_value(row))


class SkillEvalRegressionCaseListCreateView(SkillEvalAdminView):
    def get(self, request):
        review_status = request.query_params.get("status")
        error = _validate_status(review_status, {"DRAFT", "APPROVED", "REJECTED"})
        if error:
            return error
        return Response({"items": _json_value(
            SkillEvalRegressionCaseRepository.list_all(review_status=review_status)
        )})

    def post(self, request):
        feedback_id = str(request.data.get("feedback_id") or "").strip() or None
        feedback = None
        try:
            scope, team_id, skill_name, tags, polarity, document = _case_payload(request.data)
            dataset_version = _dataset_version(request.data)
            if feedback_id:
                feedback = SkillEvalFeedbackRepository.get(feedback_id)
                if feedback["review_status"] != "PENDING":
                    raise ValueError("이미 처리된 신고입니다.")
                if team_id and team_id != feedback["team_id"]:
                    raise ValueError("신고와 다른 팀의 사례로 전환할 수 없습니다.")
                if scope != "GLOBAL":
                    team_id = team_id or feedback["team_id"]
            row = SkillEvalRegressionCaseRepository.create_draft(
                case_id=str(uuid4()), scope=scope, team_id=team_id,
                skill_name=skill_name, capability_tags=tags, polarity=polarity,
                case_document=document,
                source_trace_hash=feedback["source_trace_hash"] if feedback else None,
                source_feedback_id=feedback_id,
                dataset_version=dataset_version,
            )
        except (ValueError, RegressionPrivacyError) as exc:
            return Response({"detail": str(exc)}, status=400)
        except SkillEvalFeedbackNotFound as exc:
            return Response({"detail": str(exc)}, status=404)
        return Response(_json_value(row), status=201)


class SkillEvalRegressionCaseDetailView(SkillEvalAdminView):
    def patch(self, request, case_id):
        action = request.data.get("action")
        try:
            if action in {"approve", "reject"}:
                if action == "approve":
                    current = SkillEvalRegressionCaseRepository.get(case_id)
                    validate_regression_case_shape({
                        **current["case_document"], "polarity": current["polarity"],
                    })
                row = SkillEvalRegressionCaseRepository.review(
                    case_id, reviewed_by=request.user.account_id, approve=action == "approve"
                )
            elif action == "update":
                scope, team_id, skill_name, tags, polarity, document = _case_payload(request.data)
                row = SkillEvalRegressionCaseRepository.update_draft(
                    case_id, scope=scope, team_id=team_id, skill_name=skill_name,
                    case_document=document, capability_tags=tags, polarity=polarity,
                    dataset_version=_dataset_version(request.data),
                )
            else:
                return Response({"detail": "지원하지 않는 처리입니다."}, status=400)
        except (ValueError, RegressionPrivacyError) as exc:
            return Response({"detail": str(exc)}, status=400)
        except SkillEvalRegressionCaseNotFound as exc:
            return Response({"detail": str(exc)}, status=404)
        return Response(_json_value(row))
