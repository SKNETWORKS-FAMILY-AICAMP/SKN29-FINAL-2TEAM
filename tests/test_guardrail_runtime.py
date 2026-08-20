"""등록된 가드레일을 실제 대화에 적용하는 부분(`services/guardrails`).

외부 호출과 DB 는 전부 mock 한다 — 이 저장소는 psycopg 직결이고, 테스트가 실제
OpenAI/Azure 를 부르면 안 된다(2026-08-12 에 실제로 부르고 있던 전례가 있다).

가장 중요하게 보는 것은 **언제 부르지 않는가**다. 등록이 없거나 「연결 확인」을
안 거친 것을 부르면 매 발화가 실패로 끝난다.
"""

from unittest.mock import patch

from django.test import SimpleTestCase

from services.guardrails import check_user_input
from services.guardrails.providers import GuardrailVerdict, ProviderError
from services.guardrails.providers import azure


def provider(**overrides):
    row = {
        "provider_id": "GP001",
        "team_id": "TE001",
        "name": "우리 회사 가드레일",
        "kind": "AZURE_CONTENT_SAFETY",
        "config": {"endpoint": "https://example.cognitiveservices.azure.com"},
        "status": "CONNECTED",
    }
    row.update(overrides)
    return row


@patch("services.guardrails.input_check.GuardrailEventRepository")
@patch("services.guardrails.input_check.GuardrailProviderRepository")
class WhenNotToCallTests(SimpleTestCase):
    @patch("services.guardrails.input_check.check")
    def test_등록이_없으면_부르지_않는다(self, called, repo, _events):
        repo.for_team.return_value = None

        outcome = check_user_input("안녕하세요", team_id="TE001")

        self.assertFalse(outcome.blocked)
        called.assert_not_called()

    @patch("services.guardrails.input_check.check")
    def test_연결_확인_전이면_부르지_않는다(self, called, repo, _events):
        """`UNCHECKED` 를 부르면 매 발화가 실패로 끝나고, 팀은 이유를 모른다."""

        repo.for_team.return_value = provider(status="UNCHECKED")

        outcome = check_user_input("안녕하세요", team_id="TE001")

        self.assertFalse(outcome.blocked)
        called.assert_not_called()

    @patch("services.guardrails.input_check.check")
    def test_연결_실패_상태도_부르지_않는다(self, called, repo, _events):
        repo.for_team.return_value = provider(status="ERROR")

        check_user_input("안녕하세요", team_id="TE001")

        called.assert_not_called()


@patch("services.guardrails.input_check.GuardrailEventRepository")
@patch("services.guardrails.input_check.GuardrailProviderRepository")
class VerdictTests(SimpleTestCase):
    @patch("services.guardrails.input_check.check")
    def test_통과하면_막지_않는다(self, called, repo, events):
        repo.for_team.return_value = provider()
        called.return_value = GuardrailVerdict(blocked=False)

        outcome = check_user_input("이번 주 회의록 정리해줘", team_id="TE001")

        self.assertFalse(outcome.blocked)
        events.record.assert_not_called()

    @patch("services.guardrails.input_check.check")
    def test_막히면_기록에_남기고_사유를_준다(self, called, repo, events):
        repo.for_team.return_value = provider()
        called.return_value = GuardrailVerdict(blocked=True, detail={"category": "Hate", "severity": 6})

        outcome = check_user_input("...", team_id="TE001", account_id="UA001")

        self.assertTrue(outcome.blocked)
        _, kwargs = events.record.call_args
        self.assertEqual(kwargs["action"], "BLOCKED")
        self.assertEqual(kwargs["detail"]["kind"], "AZURE_CONTENT_SAFETY")
        self.assertEqual(kwargs["detail"]["category"], "Hate")

    @patch("services.guardrails.input_check.check")
    def test_부르지_못하면_통과시킨다(self, called, repo, _events):
        """외부 검사기가 흔들릴 때마다 채팅이 막히면 가드레일이 장애 원인이 된다."""

        repo.for_team.return_value = provider()
        called.side_effect = ProviderError("연결하지 못했습니다: ConnectError")

        outcome = check_user_input("안녕하세요", team_id="TE001")

        self.assertFalse(outcome.blocked)


class AzureThresholdTests(SimpleTestCase):
    """Azure 는 심각도가 0·2·4·6 눈금이다 — 0~1 점수를 쓰는 다른 공급자와 다르다."""

    def _payload(self, severity):
        return {
            "blocklistsMatch": [],
            "categoriesAnalysis": [{"category": "Violence", "severity": severity}],
        }

    @patch("httpx.post")
    def test_기준_미만이면_통과(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = self._payload(2)

        verdict = azure.check(
            text="x", config={"endpoint": "https://a.b"}, credential={"api_key": "k"}
        )

        self.assertFalse(verdict.blocked)

    @patch("httpx.post")
    def test_기준_이상이면_차단(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = self._payload(6)

        verdict = azure.check(
            text="x", config={"endpoint": "https://a.b"}, credential={"api_key": "k"}
        )

        self.assertTrue(verdict.blocked)
        self.assertEqual(verdict.detail["severity"], 6)

    @patch("httpx.post")
    def test_눈금_밖_기준값은_기본값으로_돌린다(self, post):
        """0 을 넣으면 모든 발화가 막힌다 — 설정 실수를 그대로 따르지 않는다."""

        post.return_value.status_code = 200
        post.return_value.json.return_value = self._payload(2)

        verdict = azure.check(
            text="x",
            config={"endpoint": "https://a.b", "severity_threshold": 0},
            credential={"api_key": "k"},
        )

        self.assertFalse(verdict.blocked)

    @patch("httpx.post")
    def test_차단_목록에_걸리면_심각도와_무관하게_막는다(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {
            "blocklistsMatch": [{"blocklistName": "사내금칙어"}],
            "categoriesAnalysis": [{"category": "Violence", "severity": 0}],
        }

        verdict = azure.check(
            text="x", config={"endpoint": "https://a.b"}, credential={"api_key": "k"}
        )

        self.assertTrue(verdict.blocked)
        self.assertEqual(verdict.detail["rule"], "blocklist")

    @patch("httpx.post")
    def test_응답이_정상이_아니면_부른_쪽에_알린다(self, post):
        post.return_value.status_code = 401

        with self.assertRaises(ProviderError):
            azure.check(text="x", config={"endpoint": "https://a.b"}, credential={"api_key": "k"})
