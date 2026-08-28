"""sensitive_text.py(match_category, mask_sensitive) 단위 테스트.

`memory/write_guard.py`가 이미 이 모듈의 패턴을 재사용하고
(`tests/test_memory_write_guard.py`가 카테고리 판단 자체의 회귀 테스트),
여기서는 이 모듈 자체의 계약 — 특히 `mask_sensitive()`가 새로 추가하는
"여러 매치를 전부 가리는지", "매칭 원문이 결과에 안 남는지" — 를 본다.
"""

from django.test import SimpleTestCase

from services.agent_runtime.sensitive_text import (
    EXPORT_PLACEHOLDERS,
    MASK_PLACEHOLDER,
    mask_for_export,
    mask_for_storage,
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

    def test_current_api_key_formats_are_masked(self):
        """접두사가 붙은 현행 키 형식. 2026-08-20 실측에서 전부 통과하던 것들이다.

        옛 패턴이 `sk-` 뒤에 영숫자 **연속** 20자를 요구해서, 4자 만에 하이픈이
        나오는 `sk-proj-` 류를 못 잡았다 — 이 저장소 `.env` 의 키가 그 형식이라
        사용자가 채팅에 붙여넣으면 모델과 장기 메모리로 그대로 갔다.
        """

        keys = [
            "sk-proj-AbCdEf1234567890abcdefGHIJ",
            "sk-svcacct-AbCdEf1234567890abcdef",
            "sk-ant-api03-AbCdEf1234567890abcdef",
            "AIzaSyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q",
        ]
        for key in keys:
            with self.subTest(key=key):
                result = mask_sensitive(f"키는 {key} 입니다")
                self.assertNotIn(key, result)

    def test_ordinary_hyphenated_words_are_not_masked(self):
        """하이픈을 허용하면서 오탐이 늘지 않았는지 본다."""

        for text in ("skn29-final-2team 저장소를 봐줘", "sk-1 이라고 적혀 있어"):
            with self.subTest(text=text):
                self.assertEqual(mask_sensitive(text), text)

    def test_masked_result_never_contains_the_original_matched_value(self):
        secrets = [
            "sk-abcdefghijklmnopqrstuvwxyz1234",
            "sk-proj-AbCdEf1234567890abcdefGHIJ",
            "AKIAABCDEFGHIJKLMNOP",
            "AIzaSyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q",
            "900101-1234567",
            "1234-5678-9012-3456",
        ]
        for secret in secrets:
            with self.subTest(secret=secret):
                result = mask_sensitive(f"이 값을 기억해줘: {secret}")
                self.assertNotIn(secret, result)


class MaskForExportTests(SimpleTestCase):
    """`mask_for_export()` — Langfuse로 나가는 사본 전용 조합.

    `mask_sensitive()`와 두 가지가 다르다: 이메일을 **포함**하고, 권한 서술
    (`AUTHORITY_KEYWORDS`)은 **제외**한다. 둘 다 의도된 차이라 회귀로 잡는다.
    """

    def test_email_is_masked(self):
        self.assertEqual(
            mask_for_export("담당자 kim.jihun@example.com"),
            f"담당자 {EXPORT_PLACEHOLDERS['email']}",
        )

    def test_credential_is_masked(self):
        masked = mask_for_export("api_key: sk-abcdefghijklmnopqrstuvwx")
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwx", masked)
        self.assertIn(EXPORT_PLACEHOLDERS["credential"], masked)

    def test_pii_is_masked(self):
        masked = mask_for_export("연락처 010-1234-5678, 주민번호 900101-1234567")
        self.assertNotIn("010-1234-5678", masked)
        self.assertNotIn("900101-1234567", masked)

    def test_authority_phrase_is_kept(self):
        """trace는 디버깅용이라 '왜 그렇게 판단했나'를 지우면 안 된다 —
        `mask_sensitive()`는 가리지만 여기서는 그대로 둔다."""
        text = "이 계정은 관리자 권한이 없습니다"
        self.assertEqual(mask_for_export(text), text)
        self.assertNotEqual(mask_sensitive(text), text)

    def test_ordinary_sentence_passes_through(self):
        text = "9월 10일 기준 지연 업무를 정리했습니다"
        self.assertEqual(mask_for_export(text), text)


class MaskForStorageTests(SimpleTestCase):
    """`mask_for_storage()` — `ChatMessageRepository.append()` 직전 조합
    (2026-08-27, `apps/chat/api_views.py`).

    `mask_sensitive()`와 한 가지가 다르다: 권한 서술(`AUTHORITY_KEYWORDS`)은
    **제외**한다 — 값이 아니라 사용자가 무엇을 물었는지의 기록이라 이력에는
    남긴다. credential·PII는 둘 다 가린다는 점은 `mask_sensitive()`와 같다.
    """

    def test_credential_is_masked(self):
        masked = mask_for_storage("api_key: sk-abcdefghijklmnopqrstuvwx")
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwx", masked)
        self.assertIn(MASK_PLACEHOLDER, masked)

    def test_pii_is_masked(self):
        masked = mask_for_storage("연락처 010-1234-5678, 주민번호 900101-1234567")
        self.assertNotIn("010-1234-5678", masked)
        self.assertNotIn("900101-1234567", masked)

    def test_authority_phrase_is_kept(self):
        """`mask_sensitive()`는 가리지만 여기서는 그대로 둔다 — 대화 이력은
        사람이 무엇을 물었는지 남아야 한다."""
        text = "이 계정은 관리자 권한이 없습니다"
        self.assertEqual(mask_for_storage(text), text)
        self.assertNotEqual(mask_sensitive(text), text)

    def test_ordinary_sentence_passes_through(self):
        text = "9월 10일 기준 지연 업무를 정리했습니다"
        self.assertEqual(mask_for_storage(text), text)

    def test_masked_result_never_contains_the_original_matched_value(self):
        masked = mask_for_storage("제 카드번호는 1234-5678-9012-3456입니다")
        self.assertNotIn("1234-5678-9012-3456", masked)
