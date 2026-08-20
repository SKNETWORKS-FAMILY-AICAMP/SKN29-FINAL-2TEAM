"""가드레일 정책 값의 정규화·검증(`OpsPolicyRepository`).

DB를 타지 않는 순수 함수만 여기서 잰다 — 저장·감사로그 경로는 API 테스트가
Repository를 mock해서 덮는다(이 저장소는 psycopg 직결이라 Django 테스트 DB가
없다).
"""

import json
import re
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

import apps.ops.tokens as ops_tokens
from backend.db import OpsPolicyRepository
from backend.db.errors import RepositoryError

GUARDRAIL_URL = "/api/ops/policies/guardrail/"

MIGRATION = Path(__file__).resolve().parents[1] / "DB" / "migrations" / "2026-08-20_guardrail_policy.sql"


def admin_account(account_id="UA001"):
    return {
        "account_id": account_id,
        "email": "admin@halil.com",
        "display_name": "관리자",
        "password_hash": "unused",
        "account_status": "ACTIVE",
        "is_admin": True,
    }


class GuardrailPolicyNormalizeTests(SimpleTestCase):
    def test_empty_value_falls_back_to_defaults(self):
        """설정 행이 없거나 값이 깨져도 채팅이 막히면 안 된다."""

        self.assertEqual(
            OpsPolicyRepository._normalized_guardrail_policy({}),
            OpsPolicyRepository.DEFAULT_GUARDRAIL_POLICY,
        )

    def test_partial_value_is_filled_in(self):
        """항목을 나중에 추가해도 옛 값이 그대로 읽혀야 한다."""

        policy = OpsPolicyRepository._normalized_guardrail_policy({"pii": {"enabled": False}})

        self.assertFalse(policy["pii"]["enabled"])
        # 빠진 것은 기본값으로 채워져 모양이 항상 같다.
        self.assertEqual(policy["pii"]["strategy"], "redact")
        self.assertEqual(
            sorted(policy["moderation"]["thresholds"]),
            sorted(OpsPolicyRepository.MODERATION_CATEGORIES),
        )
        self.assertEqual(policy["blocked_words"], [])

    def test_unknown_strategy_falls_back(self):
        policy = OpsPolicyRepository._normalized_guardrail_policy({"pii": {"strategy": "block"}})

        self.assertEqual(policy["pii"]["strategy"], "redact")

    def test_unknown_threshold_category_is_dropped(self):
        policy = OpsPolicyRepository._normalized_guardrail_policy(
            {"moderation": {"thresholds": {"violence": 0.9, "made_up": 0.1}}}
        )

        self.assertEqual(policy["moderation"]["thresholds"]["violence"], 0.9)
        self.assertNotIn("made_up", policy["moderation"]["thresholds"])

    def test_blank_blocked_words_are_dropped(self):
        policy = OpsPolicyRepository._normalized_guardrail_policy({"blocked_words": ["대외비", "  ", ""]})

        self.assertEqual(policy["blocked_words"], ["대외비"])


class GuardrailPolicyValidateTests(SimpleTestCase):
    def test_rejects_unsupported_strategy(self):
        """`block`은 오탐 하나가 실행 전체를 죽여서 화면에 올리지 않는다."""

        with self.assertRaises(RepositoryError):
            OpsPolicyRepository._validated_guardrail_policy({"pii": {"strategy": "block"}})

    def test_rejects_threshold_out_of_range(self):
        for value in (-0.1, 1.5):
            with self.subTest(value=value):
                with self.assertRaises(RepositoryError):
                    OpsPolicyRepository._validated_guardrail_policy(
                        {"moderation": {"thresholds": {"violence": value}}}
                    )

    def test_rejects_non_numeric_threshold(self):
        """`True`는 파이썬에서 숫자로 통과하므로 따로 막는다."""

        for value in ("높음", True):
            with self.subTest(value=value):
                with self.assertRaises(RepositoryError):
                    OpsPolicyRepository._validated_guardrail_policy(
                        {"moderation": {"thresholds": {"violence": value}}}
                    )

    def test_rejects_unknown_category(self):
        with self.assertRaises(RepositoryError):
            OpsPolicyRepository._validated_guardrail_policy(
                {"moderation": {"thresholds": {"made_up": 0.5}}}
            )

    def test_rejects_blocked_words_that_are_not_a_list(self):
        with self.assertRaises(RepositoryError):
            OpsPolicyRepository._validated_guardrail_policy({"blocked_words": "대외비"})

    def test_deduplicates_and_trims_blocked_words(self):
        """중복을 남기면 저장할 때마다 "변경 없음" 판정이 어긋난다."""

        policy = OpsPolicyRepository._validated_guardrail_policy(
            {"blocked_words": [" 대외비 ", "대외비", "인사평가"]}
        )

        self.assertEqual(policy["blocked_words"], ["대외비", "인사평가"])


@patch("apps.ops.authentication.AccountRepository.find_credentials_by_id", return_value=admin_account())
@patch("apps.ops.views.policies.OpsPolicyRepository")
class GuardrailPolicyApiTests(SimpleTestCase):
    """운영자 콘솔의 가드레일 정책 API.

    멘토링 §16·§17이 Guardrail 을 **운영자가 화면에서 정하는 플랫폼 기능**으로
    적었다(정본: docs/작업기록/2026-08-20_가드레일_조사와_실측.md §0).
    """

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {ops_tokens.issue_token('UA001')}"}

    def test_정책_한_벌을_그대로_준다(self, policies, _admin):
        policies.get_guardrail_policy.return_value = OpsPolicyRepository.DEFAULT_GUARDRAIL_POLICY

        body = self.client.get(GUARDRAIL_URL, **self._headers()).json()

        self.assertTrue(body["pii"]["enabled"])
        self.assertEqual(body["pii"]["strategy"], "redact")
        self.assertIn("violence", body["moderation"]["thresholds"])

    def test_저장은_누가_왜_바꿨는지까지_넘긴다(self, policies, _admin):
        """감사 기록이 남아야 임계값을 왜 올렸는지 나중에 설명할 수 있다."""

        policies.set_guardrail_policy.return_value = OpsPolicyRepository.DEFAULT_GUARDRAIL_POLICY

        response = self.client.put(
            GUARDRAIL_URL,
            data=json.dumps({"policy": {"pii": {"enabled": False}}, "reason": "오탐 조정"}),
            content_type="application/json",
            **self._headers(),
        )

        self.assertEqual(response.status_code, 200)
        _, kwargs = policies.set_guardrail_policy.call_args
        self.assertEqual(kwargs["policy"], {"pii": {"enabled": False}})
        self.assertEqual(kwargs["actor_account_id"], "UA001")
        self.assertEqual(kwargs["reason"], "오탐 조정")

    def test_거절_사유는_한글_그대로_내려간다(self, policies, _admin):
        policies.set_guardrail_policy.side_effect = RepositoryError(
            "유해성 기준값은 0과 1 사이로 입력해 주세요."
        )

        response = self.client.put(
            GUARDRAIL_URL,
            data=json.dumps({"policy": {"moderation": {"thresholds": {"violence": 3}}}}),
            content_type="application/json",
            **self._headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "유해성 기준값은 0과 1 사이로 입력해 주세요.")

    def test_관리자가_아니면_막는다(self, _policies, admin):
        admin.return_value = {**admin_account(), "is_admin": False}

        response = self.client.get(GUARDRAIL_URL, **self._headers())

        self.assertEqual(response.status_code, 401)


class GuardrailPolicySeedTests(SimpleTestCase):
    """코드 기본값과 DB 시드값이 어긋나면 조용히 다르게 돈다.

    설정 행이 있는 환경(운영)과 없는 환경(테스트·새 DB)이 서로 다른 정책으로
    도는 상황을 막는다 — 이 저장소가 반복해서 겪은 "두 곳이 어긋남" 유형이다.
    """

    def test_migration_seed_matches_code_default(self):
        source = MIGRATION.read_text(encoding="utf-8")
        match = re.search(r"'GUARDRAIL_POLICY',\s*'(\{.*?\})'", source, re.DOTALL)
        self.assertIsNotNone(match, "마이그레이션에서 시드 JSON을 찾지 못했습니다.")

        seeded = json.loads(match.group(1))

        self.assertEqual(
            OpsPolicyRepository._normalized_guardrail_policy(seeded),
            OpsPolicyRepository.DEFAULT_GUARDRAIL_POLICY,
        )
