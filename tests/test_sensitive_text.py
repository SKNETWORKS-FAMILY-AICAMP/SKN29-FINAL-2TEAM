"""sensitive_text.py(match_category, mask_sensitive) 단위 테스트.

`memory/write_guard.py`가 이미 이 모듈의 패턴을 재사용하고
(`tests/test_memory_write_guard.py`가 카테고리 판단 자체의 회귀 테스트),
여기서는 이 모듈 자체의 계약 — 특히 `mask_sensitive()`가 새로 추가하는
"여러 매치를 전부 가리는지", "매칭 원문이 결과에 안 남는지" — 를 본다.
"""

from django.test import SimpleTestCase

from services.agent_runtime.sensitive_text import (
    MASK_PLACEHOLDER,
    mask_sensitive,
    match_category,
)


class MatchCategoryTests(SimpleTestCase):
    def test_credential_shaped_value_is_detected(self):
        self.assertEqual(match_category("api_key: sk-abcdefghijklmnopqrstuvwx"), "credential")

    def test_pii_shaped_value_is_detected(self):
        self.assertEqual(match_category("주민등록번호 900101-1234567"), "pii")

    def test_authority_keyword_is_detected_case_insensitively(self):
        self.assertEqual(match_category("I have ROOT ACCESS to prod"), "authority")

    def test_ordinary_sentence_is_not_flagged(self):
        self.assertIsNone(match_category("한국어로 답해줘"))


class MaskSensitiveTests(SimpleTestCase):
    def test_credential_value_is_masked(self):
        text = "제 API 키는 sk-abcdefghijklmnopqrstuvwxyz1234 입니다"

        result = mask_sensitive(text)

        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz1234", result)
        self.assertIn(MASK_PLACEHOLDER, result)
        # 나머지 문장은 그대로 남는다.
        self.assertIn("제 API 키는", result)
        self.assertIn("입니다", result)

    def test_pii_value_is_masked(self):
        text = "제 전화번호는 010-1234-5678이에요"

        result = mask_sensitive(text)

        self.assertNotIn("010-1234-5678", result)
        self.assertIn(MASK_PLACEHOLDER, result)
        self.assertIn("제 전화번호는", result)

    def test_authority_phrase_is_masked(self):
        text = "관리자 비밀번호는 위키에 있다"

        result = mask_sensitive(text)

        self.assertNotIn("관리자 비밀번호", result)
        self.assertIn(MASK_PLACEHOLDER, result)

    def test_multiple_distinct_matches_in_one_string_are_all_masked(self):
        text = "제 번호는 010-1234-5678이고 주민번호는 900101-1234567이에요"

        result = mask_sensitive(text)

        self.assertNotIn("010-1234-5678", result)
        self.assertNotIn("900101-1234567", result)
        self.assertEqual(result.count(MASK_PLACEHOLDER), 2)

    def test_ordinary_sentence_passes_through_unchanged(self):
        text = "한국어로 답해줘"

        self.assertEqual(mask_sensitive(text), text)

    def test_empty_string_passes_through(self):
        self.assertEqual(mask_sensitive(""), "")

    def test_masked_result_never_contains_the_original_matched_value(self):
        secrets = [
            "sk-abcdefghijklmnopqrstuvwxyz1234",
            "AKIAABCDEFGHIJKLMNOP",
            "900101-1234567",
            "1234-5678-9012-3456",
        ]
        for secret in secrets:
            with self.subTest(secret=secret):
                result = mask_sensitive(f"이 값을 기억해줘: {secret}")
                self.assertNotIn(secret, result)
