from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.ops.authentication import Admin
from apps.ops.views.skill_eval import (
    SkillEvalFeedbackDetailView,
    SkillEvalRegressionCaseDetailView,
    SkillEvalRegressionCaseListCreateView,
)
from apps.chat.api_views import SkillFeedbackAPIView

from services.agent_runtime.skills.evaluation.name_suggester import suggest_names
from services.agent_runtime.skills.evaluation.privacy import RegressionPrivacyError, validate_anonymized_case
from services.agent_runtime.skills.evaluation.rate_limit import _ProviderLimiter
from services.agent_runtime.skills.evaluation.platform_probes import load_platform_probes
from services.agent_runtime.skills.versioning import tool_registry_version, validation_hash
from services.harness.registry import BUILTIN_TOOLS, Tool
from backend.db.skill_eval import SkillEvalRegressionCaseRepository


class PrivacyGuardTests(SimpleTestCase):
    def test_anonymized_case_is_accepted(self):
        validate_anonymized_case({
            "polarity": "positive",
            "messages": [{"role": "user", "content": "합성된 요청입니다."}],
        })

    def test_obvious_identifier_is_rejected(self):
        with self.assertRaises(RegressionPrivacyError):
            validate_anonymized_case({
                "polarity": "negative",
                "messages": [{"role": "user", "content": "연락처는 person@example.com입니다."}],
            })

    def test_versioned_platform_probes_pass_schema_and_privacy_checks(self):
        version, cases = load_platform_probes()
        self.assertTrue(version)
        self.assertEqual(len({case["case_id"] for case in cases}), len(cases))


class ValidationHashTests(SimpleTestCase):
    def test_execution_frontmatter_changes_hash(self):
        base = {
            "name": "sample-skill", "description": "설명", "body": "절차",
            "frontmatter": {"name": "sample-skill", "description": "설명", "allowed-tools": ["tool-a"]},
        }
        changed = {**base, "frontmatter": {**base["frontmatter"], "allowed-tools": ["tool-b"]}}
        self.assertNotEqual(validation_hash(base), validation_hash(changed))

    def test_storage_metadata_does_not_change_hash(self):
        base = {"name": "sample-skill", "description": "설명", "body": "절차"}
        stored = {
            **base,
            "frontmatter": {
                "name": "sample-skill", "description": "설명",
                "metadata": {"enabled": "false", "shared_by_account_id": "AC001", "source_job_id": "job-1"},
            },
        }
        self.assertEqual(validation_hash(base), validation_hash(stored))

    def test_tool_input_schema_changes_registry_version(self):
        common = {
            "ref": "schema-probe",
            "name": "검사용 도구",
            "description": "입력 계약 변경 감지",
            "handler": lambda **_kwargs: None,
        }
        first = Tool(
            **common,
            input_schema={"type": "object", "properties": {"a": {"type": "string"}}},
        )
        second = Tool(
            **common,
            input_schema={"type": "object", "properties": {"a": {"type": "integer"}}},
        )
        with patch.dict(BUILTIN_TOOLS, {"schema-probe": first}, clear=True):
            first_version = tool_registry_version()
        with patch.dict(BUILTIN_TOOLS, {"schema-probe": second}, clear=True):
            second_version = tool_registry_version()

        self.assertNotEqual(first_version, second_version)


class NameSuggestionTests(SimpleTestCase):
    @patch("services.agent_runtime.skills.evaluation.name_suggester.ModelFactory")
    @patch("services.agent_runtime.skills.evaluation.name_suggester.ModelConfigResolver")
    def test_model_output_is_validated_and_deduplicated(self, resolver, factory):
        resolver.return_value.resolve.return_value = MagicMock()
        result = MagicMock(names=["better-skill", "better-skill", "Bad Name"])
        factory.return_value.create.return_value.with_structured_output.return_value.invoke.return_value = result
        self.assertEqual(suggest_names({"name": "old-skill", "description": "설명", "body": "절차"}), ["better-skill"])


class ProviderLimiterTests(SimpleTestCase):
    @override_settings(SKILL_VALIDATION_PROVIDER_MAX_CONCURRENCY=1, SKILL_VALIDATION_PROVIDER_REQUESTS_PER_MINUTE=100)
    def test_provider_capacity_is_isolated_by_provider(self):
        limiter = _ProviderLimiter()
        entered = Event()
        release = Event()

        def hold_first():
            with limiter.slot("provider-a", deadline=monotonic() + 2):
                entered.set()
                release.wait(1)

        with ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(hold_first)
            self.assertTrue(entered.wait(1))
            with limiter.slot("provider-b", deadline=monotonic() + 1):
                pass
            release.set()
            future.result(timeout=2)


class RegressionCaseOpsApiTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = Admin(account_id="AC001", email="admin@example.invalid", display_name="관리자")

    @patch("apps.ops.views.skill_eval.SkillEvalRegressionCaseRepository.create_draft")
    def test_operator_can_only_create_anonymized_draft(self, create_draft):
        create_draft.return_value = {"case_id": "case-1", "review_status": "DRAFT"}
        request = self.factory.post("/", {
            "scope": "GLOBAL", "polarity": "negative", "capability_tags": ["general"],
            "case_document": {"messages": [{"role": "user", "content": "합성된 요청"}]},
        }, format="json")
        force_authenticate(request, user=self.admin)
        response = SkillEvalRegressionCaseListCreateView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        create_draft.assert_called_once()
        stored = create_draft.call_args.kwargs["case_document"]
        self.assertFalse(stored["should_activate_candidate"])
        self.assertEqual(stored["required_tools"], [])

    @patch("apps.ops.views.skill_eval.SkillEvalFeedbackRepository.get")
    @patch("apps.ops.views.skill_eval.SkillEvalRegressionCaseRepository.create_draft")
    def test_global_case_from_feedback_does_not_inherit_source_team(self, create_draft, get_feedback):
        get_feedback.return_value = {
            "review_status": "PENDING", "team_id": "TM001", "source_trace_hash": "hash",
        }
        create_draft.return_value = {"case_id": "case-1", "review_status": "DRAFT"}
        request = self.factory.post("/", {
            "feedback_id": "feedback-1", "scope": "GLOBAL", "polarity": "negative",
            "case_document": {"messages": [{"role": "user", "content": "합성된 요청"}]},
        }, format="json")
        force_authenticate(request, user=self.admin)

        response = SkillEvalRegressionCaseListCreateView.as_view()(request)

        self.assertEqual(response.status_code, 201)
        self.assertIsNone(create_draft.call_args.kwargs["team_id"])

    @patch("apps.ops.views.skill_eval.SkillEvalRegressionCaseRepository.create_draft")
    def test_raw_identifier_blocks_case_creation(self, create_draft):
        request = self.factory.post("/", {
            "scope": "GLOBAL", "polarity": "negative",
            "case_document": {"messages": [{"role": "user", "content": "person@example.com"}]},
        }, format="json")
        force_authenticate(request, user=self.admin)
        response = SkillEvalRegressionCaseListCreateView.as_view()(request)
        self.assertEqual(response.status_code, 400)
        create_draft.assert_not_called()

    @patch("apps.ops.views.skill_eval.SkillEvalRegressionCaseRepository.review")
    @patch("apps.ops.views.skill_eval.SkillEvalRegressionCaseRepository.get")
    def test_approval_revalidates_stored_document(self, get_case, review):
        get_case.return_value = {
            "polarity": "positive",
            "case_document": {
                "polarity": "positive", "category": "direct",
                "messages": [{"role": "user", "content": "합성된 요청"}],
                "document_fixtures": [], "tool_fixtures": {},
                "should_activate_candidate": True, "allowed_other_skill_names": [],
                "required_tools": [], "forbidden_tools": [], "approval_fixtures": [],
                "behavior_assertions": [], "reason": "검증 이유",
            }
        }
        review.return_value = {"case_id": "case-1", "review_status": "APPROVED"}
        request = self.factory.patch("/", {"action": "approve"}, format="json")
        force_authenticate(request, user=self.admin)
        response = SkillEvalRegressionCaseDetailView.as_view()(request, case_id="case-1")
        self.assertEqual(response.status_code, 200)
        review.assert_called_once_with("case-1", reviewed_by="AC001", approve=True)

    @patch("apps.ops.views.skill_eval.SkillEvalRegressionCaseRepository.review")
    @patch("apps.ops.views.skill_eval.SkillEvalRegressionCaseRepository.get")
    def test_incomplete_legacy_draft_cannot_be_approved(self, get_case, review):
        get_case.return_value = {
            "polarity": "positive",
            "case_document": {"messages": [{"role": "user", "content": "합성된 요청"}]},
        }
        request = self.factory.patch("/", {"action": "approve"}, format="json")
        force_authenticate(request, user=self.admin)
        response = SkillEvalRegressionCaseDetailView.as_view()(request, case_id="case-1")
        self.assertEqual(response.status_code, 400)
        review.assert_not_called()

    @patch("apps.ops.views.skill_eval.SkillEvalRegressionCaseRepository.update_draft")
    def test_draft_update_changes_scope_and_document_together(self, update):
        update.return_value = {"case_id": "case-1", "review_status": "DRAFT"}
        request = self.factory.patch("/", {
            "action": "update", "scope": "TEAM", "team_id": "TM001",
            "polarity": "negative", "capability_tags": ["workflow"],
            "dataset_version": "v2",
            "case_document": {"messages": [{"role": "user", "content": "합성된 요청"}]},
        }, format="json")
        force_authenticate(request, user=self.admin)
        response = SkillEvalRegressionCaseDetailView.as_view()(request, case_id="case-1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(update.call_args.kwargs["scope"], "TEAM")
        self.assertEqual(update.call_args.kwargs["team_id"], "TM001")
        self.assertEqual(update.call_args.kwargs["dataset_version"], "v2")

    @patch("apps.ops.views.skill_eval.SkillEvalFeedbackRepository.dismiss")
    def test_feedback_can_be_dismissed_without_creating_regression_case(self, dismiss):
        dismiss.return_value = {"feedback_id": "feedback-1", "review_status": "DISMISSED"}
        request = self.factory.patch("/", {"action": "dismiss"}, format="json")
        force_authenticate(request, user=self.admin)
        response = SkillEvalFeedbackDetailView.as_view()(request, feedback_id="feedback-1")
        self.assertEqual(response.status_code, 200)
        dismiss.assert_called_once_with("feedback-1", reviewed_by="AC001")


class RegressionRepositoryScopeTests(SimpleTestCase):
    @patch("backend.db.skill_eval.database_connection")
    def test_exact_skill_case_does_not_cross_team_boundary(self, database_connection):
        connection = database_connection.return_value.__enter__.return_value
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = []
        SkillEvalRegressionCaseRepository.list_approved_for(
            team_id="TM001", skill_name="same-name", capability_tags=["workflow"]
        )
        sql, params = cursor.execute.call_args.args
        self.assertIn("scope = 'SKILL'", sql)
        self.assertIn("team_id IS NULL OR team_id = %s", sql)
        self.assertEqual(params, ("same-name", "TM001", "TM001", ["workflow"]))


class SkillFeedbackApiTests(SimpleTestCase):
    @patch("backend.db.skill_eval.SkillEvalFeedbackRepository.create")
    def test_user_can_report_answer_without_copying_raw_message(self, create):
        create.return_value = ({"feedback_id": "feedback-1", "review_status": "PENDING"}, True)
        request = APIRequestFactory().post("/", {"feedback_kind": "WRONG_USAGE"}, format="json")
        user = MagicMock(account_id="AC001", is_authenticated=True)
        force_authenticate(request, user=user)
        response = SkillFeedbackAPIView.as_view()(request, message_id="message-1")
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("content", create.call_args.kwargs)
        create.assert_called_once_with(
            message_id="message-1", account_id="AC001", feedback_kind="WRONG_USAGE",
            expected_skill=None, note=None,
        )
