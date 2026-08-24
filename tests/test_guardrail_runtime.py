"""등록된 가드레일을 실제 대화에 적용하는 부분(`services/guardrails`).

외부 호출과 DB 는 전부 mock 한다 — 이 저장소는 psycopg 직결이고, 테스트가 실제
OpenAI/Azure 를 부르면 안 된다(2026-08-12 에 실제로 부르고 있던 전례가 있다).

가장 중요하게 보는 것은 **언제 부르지 않는가**다. 등록이 없거나 「연결 확인」을
안 거친 것을 부르면 매 발화가 실패로 끝난다.
"""

import json
from unittest.mock import patch

from django.test import SimpleTestCase

from services.guardrails import check_user_input, on_check_timeout
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
        "is_active": True,
        "on_failure": "OPEN",
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


class OpenAIGuardrailsReasonTests(SimpleTestCase):
    """실패 사유를 운영자가 고칠 수 있는 말로 바꾼다.

    `run_guardrails` 는 실패를 `ExceptionGroup` 으로 묶고 그 안은 평범한
    `Exception` 이라, 손대지 않으면 화면에 「ExceptionGroup」만 뜬다(2026-08-20 실측).
    """

    def test_키가_틀리면_그렇게_말한다(self):
        from services.guardrails.providers.openai_guardrails import _reason

        inner = Exception(
            "Error code: 401 - {'error': {'message': 'Incorrect API key provided: sk-abc*****xyz'}}"
        )

        self.assertEqual(_reason(ExceptionGroup("g", [inner])), "키가 올바르지 않습니다.")

    def test_예외_문자열을_그대로_내보내지_않는다(self):
        """OpenAI 가 가려 주긴 해도 그 안에 키 조각이 있다."""

        from services.guardrails.providers.openai_guardrails import _reason

        inner = Exception("Error code: 401 - Incorrect API key provided: sk-abc*****xyz")

        self.assertNotIn("sk-abc", _reason(ExceptionGroup("g", [inner])))

    def test_한도_초과도_구분한다(self):
        from services.guardrails.providers.openai_guardrails import _reason

        reason = _reason(ExceptionGroup("g", [Exception("Error code: 429 - rate limit")]))

        self.assertIn("한도", reason)

    def test_중첩된_그룹도_푼다(self):
        from services.guardrails.providers.openai_guardrails import _reason

        nested = ExceptionGroup("outer", [ExceptionGroup("inner", [Exception("Error code: 401 -")])])

        self.assertEqual(_reason(nested), "키가 올바르지 않습니다.")


@patch("services.guardrails.input_check.GuardrailEventRepository")
@patch("services.guardrails.input_check.GuardrailProviderRepository")
class ActiveOnlyTests(SimpleTestCase):
    """여러 개 등록해 두고 **활성인 하나만** 쓴다.

    `for_team()` 이 활성만 돌려주므로 런타임은 고를 필요가 없다 — 이 테스트는 그
    계약을 고정한다. 등록만 해 둔 것(보관·교체 대기)을 부르면 그 팀의 대화가
    쓰지 않기로 한 가드레일을 거친다.
    """

    @patch("services.guardrails.input_check.check")
    def test_활성이_없으면_부르지_않는다(self, called, repo, _events):
        repo.for_team.return_value = None

        outcome = check_user_input("안녕하세요", team_id="TE001")

        self.assertFalse(outcome.blocked)
        called.assert_not_called()

    @patch("services.guardrails.input_check.check")
    def test_활성인_것을_그대로_쓴다(self, called, repo, _events):
        repo.for_team.return_value = provider(name="지금 쓰는 것")
        called.return_value = GuardrailVerdict(blocked=False)

        check_user_input("안녕하세요", team_id="TE001")

        # 고르는 일은 저장소가 한다 — 런타임은 팀만 넘긴다.
        repo.for_team.assert_called_once_with("TE001")
        _, kwargs = called.call_args
        self.assertEqual(kwargs["kind"], "AZURE_CONTENT_SAFETY")


class ProviderTimeoutTests(SimpleTestCase):
    """**세 공급자 모두 호출에 상한이 있어야 한다.**

    「호출이 안 되는」 경우는 이미 통과로 처리한다(`test_부르지_못하면_통과시킨다`).
    더 위험한 것은 **「느리게 되는」** 경우다 — openai SDK 기본값은 600초에 재시도
    2회라, 상한을 안 주면 사용자 발화가 최악 30분 붙들린다. 그건 실패가 아니라
    응답 없음이라 fail-open 도 안 걸린다.
    """

    def test_세_공급자가_같은_상한을_쓴다(self):
        from services.guardrails.providers import azure, bedrock, openai_guardrails

        self.assertEqual(
            {azure.TIMEOUT_SECONDS, bedrock.TIMEOUT_SECONDS, openai_guardrails.TIMEOUT_SECONDS},
            {10},
        )

    def test_openai_클라이언트에_상한과_재시도_없음을_준다(self):
        """기본값을 그대로 쓰면 상한이 사실상 없는 것과 같다."""

        import sys
        from unittest.mock import MagicMock

        from services.guardrails.providers import openai_guardrails as mod

        made = MagicMock()
        fake_openai = MagicMock(AsyncOpenAI=made)
        fake_guardrails = MagicMock(load_pipeline_bundles=MagicMock(side_effect=RuntimeError("여기까지만")))

        with patch.dict(sys.modules, {"openai": fake_openai, "guardrails": fake_guardrails}):
            with self.assertRaises(ProviderError):
                # 설정을 못 읽는 데서 멈춘다 — 클라이언트를 만들기 전이라
                # 이 경로로는 확인이 안 된다. 그래서 정상 설정으로 다시 부른다.
                mod.check(text="x", config={"pipeline": "{}"}, credential={"api_key": "k"})

        fake_guardrails.load_pipeline_bundles.side_effect = None
        fake_guardrails.instantiate_guardrails.return_value = []
        with patch.dict(sys.modules, {"openai": fake_openai, "guardrails": fake_guardrails}):
            try:
                mod.check(text="x", config={"pipeline": "{}"}, credential={"api_key": "k"})
            except ProviderError:
                pass

        _, kwargs = made.call_args
        self.assertEqual(kwargs["timeout"], mod.TIMEOUT_SECONDS)
        self.assertEqual(kwargs["max_retries"], 0)


@patch("services.guardrails.input_check.GuardrailEventRepository")
@patch("services.guardrails.input_check.GuardrailProviderRepository")
class WhenTheCheckerIsDownTests(SimpleTestCase):
    """검사기를 못 불렀을 때. **무엇을 할지는 그 팀이 정한다**(`on_failure`).

    우리가 임시 검사를 대신 돌리지는 않는다 — 고객이 동의한 적 없는 기준으로
    막는 것이고, 문의가 오면 「왜 막혔나」에 답할 수 없다(2026-08-20 PM 논의).
    """

    @patch("services.guardrails.input_check.check")
    def test_통과를_고른_팀은_그대로_보낸다(self, called, repo, _events):
        repo.for_team.return_value = provider(on_failure="OPEN")
        called.side_effect = ProviderError("연결하지 못했습니다: ConnectError")

        self.assertFalse(check_user_input("안녕하세요", team_id="TE001").blocked)

    @patch("services.guardrails.input_check.check")
    def test_막음을_고른_팀은_보내지_않는다(self, called, repo, _events):
        repo.for_team.return_value = provider(on_failure="CLOSED")
        called.side_effect = ProviderError("연결하지 못했습니다: ConnectError")

        outcome = check_user_input("안녕하세요", team_id="TE001")

        self.assertTrue(outcome.blocked)
        # **표현을 바꾸라고 하면 안 된다** — 발화 탓이 아니다.
        self.assertNotIn("표현을 바꿔", outcome.blocked_reason)

    @patch("services.guardrails.input_check.check")
    def test_어느_쪽이든_기록에_남는다(self, called, repo, events):
        """지금까지는 로그 한 줄이 전부라, 검사가 통째로 빠져도 콘솔은
        마지막 「연결 확인」 결과인 「연결됨」을 계속 보여줬다."""

        repo.for_team.return_value = provider(on_failure="OPEN")
        called.side_effect = ProviderError("연결하지 못했습니다: ConnectError")

        check_user_input("안녕하세요", team_id="TE001", account_id="UA001")

        _, kwargs = events.record.call_args
        self.assertEqual(kwargs["action"], "SKIPPED")
        self.assertEqual(kwargs["rule"], "PROVIDER")
        self.assertEqual(kwargs["detail"]["kind"], "AZURE_CONTENT_SAFETY")
        self.assertFalse(kwargs["detail"]["blocked"])

    @patch("services.guardrails.input_check.check")
    def test_기록에_원문은_안_담는다(self, called, repo, events):
        repo.for_team.return_value = provider(on_failure="CLOSED")
        called.side_effect = ProviderError("연결하지 못했습니다: ConnectError")

        check_user_input("주민번호는 900101-1234567 입니다", team_id="TE001")

        _, kwargs = events.record.call_args
        self.assertNotIn("900101", json.dumps(kwargs["detail"], ensure_ascii=False))

    def test_기다리다_포기해도_같은_판단을_한다(self, repo, events):
        """검사기가 죽는 대신 **응답을 안 하는** 갈래. 여기서 통과로 고정하면
        「막음」을 켠 팀에 구멍이 생긴다."""

        repo.for_team.return_value = provider(on_failure="CLOSED")

        outcome = on_check_timeout(team_id="TE001")

        self.assertTrue(outcome.blocked)
        self.assertEqual(events.record.call_args[1]["action"], "SKIPPED")

    def test_등록이_없으면_기다림_포기도_그냥_보낸다(self, repo, events):
        repo.for_team.return_value = None

        self.assertFalse(on_check_timeout(team_id="TE001").blocked)
        events.record.assert_not_called()


class AzureCustomerSettingsTests(SimpleTestCase):
    """**Azure 만 판정을 안 준다.** `text:analyze` 는 카테고리별 심각도만
    돌려주고 「막을지」는 부르는 쪽이 정한다(OpenAI Guardrails·Bedrock 은 저쪽이
    판정한다). 그러니 기준값은 어딘가에 있어야 하는데, 우리 코드에 박아 두면
    **우리가** 그 고객의 차단 기준을 정하는 셈이다 — 화면에서 받아 쓴다.
    """

    def _payload(self, severity):
        return {
            "blocklistsMatch": [],
            "categoriesAnalysis": [{"category": "Violence", "severity": severity}],
        }

    @patch("httpx.post")
    def test_화면에서_받은_기준값을_쓴다(self, post):
        """기본값(4)이면 통과할 심각도 2 를, 고객이 2 로 낮추면 막아야 한다."""

        post.return_value.status_code = 200
        post.return_value.json.return_value = self._payload(2)

        verdict = azure.check(
            text="x",
            # 화면은 select 값이라 문자열로 온다.
            config={"endpoint": "https://a.b", "severity_threshold": "2"},
            credential={"api_key": "k"},
        )

        self.assertTrue(verdict.blocked)
        self.assertEqual(verdict.detail["threshold"], 2)

    @patch("httpx.post")
    def test_안_고르면_기본값을_쓴다(self, post):
        """화면의 「고르지 않음」은 빈 문자열로 온다 — 0 으로 읽으면 다 막힌다."""

        post.return_value.status_code = 200
        post.return_value.json.return_value = self._payload(2)

        verdict = azure.check(
            text="x",
            config={"endpoint": "https://a.b", "severity_threshold": ""},
            credential={"api_key": "k"},
        )

        self.assertFalse(verdict.blocked)

    @patch("httpx.post")
    def test_차단_목록_이름을_그대로_넘긴다(self, post):
        """**목록 자체는 Azure 에 있다** — 우리는 이름만 들고 간다."""

        post.return_value.status_code = 200
        post.return_value.json.return_value = self._payload(0)

        azure.check(
            text="x",
            config={"endpoint": "https://a.b", "blocklists": ["ours", "theirs"]},
            credential={"api_key": "k"},
        )

        self.assertEqual(post.call_args[1]["json"]["blocklistNames"], ["ours", "theirs"])

    @patch("httpx.post")
    def test_목록이_없으면_아예_안_보낸다(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = self._payload(0)

        azure.check(text="x", config={"endpoint": "https://a.b"}, credential={"api_key": "k"})

        self.assertNotIn("blocklistNames", post.call_args[1]["json"])
