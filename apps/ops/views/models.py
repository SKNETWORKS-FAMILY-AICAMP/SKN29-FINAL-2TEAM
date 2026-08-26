"""팀별 모델 API 등록·삭제.

**팀이 스스로 등록하지 않는다.** 회사가 요청하면 운영자가 등록한다(2026-08-13 멘토링).
설정 화면의 등록 폼은 없앴다 — 등록하려면 OpenAI 호환 주소와 키와 모델 식별자를
알아야 하는데, 그건 「코딩 없이」를 내세운 제품이 비개발자에게 요구할 일이 아니다.
실제로 Google 호환 주소는 AI Studio 화면에 없어서 문서를 뒤져야 나왔다.

**권한 범위는 여전히 팀이다.** 등록하는 사람만 운영자로 바뀔 뿐, 그 모델을 고르고
실행에 쓰는 것은 그 팀뿐이다(`CustomModelRepository._rows` 가 `user_account.team_id`
로 거른다). 조직 단위로 넓히는 것은 하지 않기로 했다(2026-08-13 PM 결정).
"""

import logging

import psycopg
from rest_framework import status
from rest_framework.response import Response

from backend.api_errors import to_response
from backend.db import log_audit
from apps.agents.serializers import AGENT_MODELS
from backend.db.agent_platform import CustomModelRepository
from backend.db.errors import RepositoryError
from backend.db.repositories import TeamRepository

from ..authentication import AdminView
from ..serializers import OpsModelRegisterSerializer, ops_model_row_response

logger = logging.getLogger(__name__)


class ModelListCreateView(AdminView):
    def get(self, request):
        try:
            rows = CustomModelRepository.list_all()
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response([ops_model_row_response(row) for row in rows])

    def post(self, request):
        serializer = OpsModelRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # **같은 팀에 같은 이름을 두 번 두지 않는다.** 경로가 모델 이름 하나로
        # 정해지므로(`for_model`), 겹치면 실행은 먼저 등록한 것으로 고정되는데
        # 목록에는 둘로 보인다 — 어느 것으로 도는지 아무도 모르게 된다.
        try:
            if data["model"] in CustomModelRepository.models_for_team(data["team_id"]):
                return Response(
                    {"detail": f"{data['model']} 은 이 팀에 이미 등록돼 있습니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)

        # **등록 전에 한 번 써 본다.** 안 되는 것을 등록해 두면 그 팀의 대화가
        # 조용히 실패하고, 팀은 운영자가 등록해 줬으니 되는 줄 안다.
        error = _verify(data["api_key"], data["base_url"], data["model"])
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        # **토큰 사용량까지는 막지 않는다.** 답을 주는 것과 사용량을 알려주는
        # 것은 별개 능력이다(`services/agent_runtime/models/factory.py`의
        # `stream_usage=True` 주석 참고) — 여기서 안 된다고 등록 자체를 막으면
        # 채팅 기능은 멀쩡한 모델을 못 쓰게 만든다. 대신 등록은 그대로 두고
        # 화면에만 알린다.
        usage_supported = _check_usage_support(data["api_key"], data["base_url"], data["model"])

        try:
            CustomModelRepository.add_for_team(
                team_id=data["team_id"],
                label=data["label"],
                base_url=data["base_url"],
                api_key=data["api_key"],
                model=data["model"],
                registered_by=request.user.account_id,
            )
            # 남의 팀에 외부 호출 경로를 심는 일이라 반드시 기록에 남는다.
            # **키는 남기지 않는다** — 감사 로그는 나중에 사람이 읽는 표다.
            log_audit(
                actor_account_id=request.user.account_id,
                action="OPS_MODEL_REGISTER",
                target_type="TEAM",
                target_id=data["team_id"],
                payload={"model": data["model"], "label": data["label"], "base_url": data["base_url"]},
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        # **목록을 여기서 다시 만들지 않는다.** 만들다 실패하면 이미 끝난 등록이
        # 실패로 보고된다 — 운영자는 안 됐다고 믿고 다시 누른다(2026-08-13 검토).
        # 목록은 화면이 따로 받아 간다.
        response_body: dict[str, str] = {"team_id": data["team_id"], "model": data["model"]}
        if not usage_supported:
            response_body["warning"] = (
                "이 서버는 토큰 사용량 정보를 제공하지 않는 것으로 보입니다. "
                "등록은 완료됐지만 이 모델을 쓰는 대화의 토큰 사용량은 집계되지 않습니다."
            )
        return Response(response_body, status=status.HTTP_201_CREATED)


class TeamDefaultModelView(AdminView):
    """그 팀의 **기본 채팅 모델** — 아무 에이전트도 안 고르고 말을 걸었을 때 도는 것.

    **팀이 화면에서 고르지 않는다**(2026-08-18 멘토링). 설정의 Model 탭을
    걷어내고 여기로 옮겼다. 8/13 에 모델 **등록**을 옮긴 것의 연장이다 — 그때는
    「어떤 모델을 붙일 수 있나」였고 이번은 「기본으로 무엇을 쓰나」다.

    **전역 하나로 두지 않는다.** 계약·리전 요건이 다른 회사를 못 받는다. 그래서
    팀을 받아 그 팀에만 쓴다.

    **저장 위치는 `team.default_model` 이다**(2026-08-22). 그 전에는 레거시 정문
    에이전트(`agent_tool.tool_ref='agent:*'`)의 `agent.model` 에 얹혀 있었는데,
    레거시 `agent` 폐기와 함께 팀 설정 본래 자리로 옮겼다 — 근거는
    `DB/migrations/2026-08-22_team_default_model.sql` 헤더.

    **에이전트별 모델은 그대로 빌더에 있다**(8/18 PM 결정). 여기서 정하는 것은
    아무것도 안 고르고 말을 걸었을 때 도는 모델 하나뿐이다.
    """

    def get(self, request, team_id):
        try:
            model = TeamRepository.default_model(team_id)
            # 고를 수 있는 것을 함께 준다 — 운영자가 모델 이름을 외워 적을 자리가
            # 아니다. 오타는 실행 시점 404 가 되고, 그때 죽는 것은 그 팀의 대화다.
            customs = sorted(CustomModelRepository.models_for_team(team_id))
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(
            {
                # 정한 적이 없으면 「없다」고 말한다. 임의의 기본값을 저장된 것처럼
                # 보이면 안 된다(팀 화면에서 지켜 온 규칙 그대로다).
                "model": model,
                "choices": list(AGENT_MODELS) + customs,
            }
        )

    def put(self, request, team_id):
        model = (request.data.get("model") or "").strip()
        if not model:
            return Response({"detail": "모델이 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            allowed = set(AGENT_MODELS) | CustomModelRepository.models_for_team(team_id)
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        if model not in allowed:
            # 아무 문자열이나 받으면 저장은 되고 **실행 시점에 404 로 죽는다.**
            # 운영자는 저장됐으니 맞다고 믿고, 죽는 것은 그 팀의 대화다.
            return Response(
                {"detail": f"{model} 은 이 팀이 쓸 수 없는 모델입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            saved = TeamRepository.set_default_model(team_id=team_id, model=model)
            # 남의 팀 대화가 도는 모델을 바꾸는 일이라 기록에 남는다.
            log_audit(
                actor_account_id=request.user.account_id,
                action="OPS_TEAM_MODEL_SET",
                target_type="TEAM",
                target_id=team_id,
                payload={"model": model},
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response({"model": saved})


class ModelProbeView(AdminView):
    """주소와 키를 주면 **그 엔드포인트가 가진 모델 목록**을 돌려준다.

    **이름을 외워 적게 하지 않는다.** 오타 하나가 실행 시점 404 가 되고, 그때는
    등록해 준 우리가 아니라 그 팀의 대화가 죽는다. 운영자라고 사정이 낫지 않다 —
    고객에게 전달받은 이름을 옮겨 적는 자리라 오히려 틀리기 쉽다.

    다만 목록을 안 주는 구현도 흔하다(Anthropic 호환 경로는 401 이다). 그때는 빈
    목록과 이유를 주고, 화면이 직접 입력으로 넘어간다.
    """

    def post(self, request):
        base_url = (request.data.get("base_url") or "").strip()
        api_key = (request.data.get("api_key") or "").strip()
        if not base_url or not api_key:
            return Response(
                {"detail": "주소와 키가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=base_url, timeout=20, max_retries=0)
            names = sorted(item.id for item in client.models.list().data)
        except Exception as exc:  # noqa: BLE001 - 어떤 실패든 「여기서는 못 고른다」다
            logger.info("모델 목록 조회 실패: %s", type(exc).__name__)
            return Response(
                {"models": [], "detail": "이 주소에서 모델 목록을 받지 못했습니다. 주소와 키를 확인해 주세요."}
            )
        if not names:
            return Response({"models": [], "detail": "이 주소가 쓸 수 있는 모델을 알려주지 않았습니다."})
        return Response({"models": names, "detail": None})


class ModelDetailView(AdminView):
    def delete(self, request, conn_id):
        try:
            removed = CustomModelRepository.remove_by_conn_id(conn_id)
            # **무엇을 지웠는지 남긴다.** 행을 지우고 나면 conn_id 는 아무것도
            # 가리키지 않아서, 그 값만 남기면 나중에 「어느 팀의 무슨 모델이
            # 없어졌나」를 복원할 수 없다. 등록 쪽과 같은 모양으로 맞춘다.
            log_audit(
                actor_account_id=request.user.account_id,
                action="OPS_MODEL_REMOVE",
                target_type="TEAM",
                target_id=removed["team_id"],
                payload={"conn_id": conn_id, **{k: removed[k] for k in ("model", "label", "base_url")}},
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _verify(api_key: str, base_url: str, model: str) -> str | None:
    """그 주소·키·모델로 실제로 답이 오는가. 되면 `None`, 아니면 보여줄 이유.

    목록 조회만 되고 호출은 안 되는 엔드포인트가 흔해서, 모델 목록이 아니라
    **한 번 답을 받아 본다**.
    """

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url, timeout=25, max_retries=0)
        client.chat.completions.create(model=model, messages=[{"role": "user", "content": "hi"}])
    except Exception as exc:  # noqa: BLE001 - 어떤 실패든 「이걸로는 못 부른다」다
        logger.warning("모델 등록 확인 실패: %s", type(exc).__name__)
        return "이 주소와 모델로 답을 받지 못했습니다. 주소·키·모델 이름을 확인해 주세요."
    return None


def _check_usage_support(api_key: str, base_url: str, model: str) -> bool:
    """스트리밍 응답에 실제로 토큰 사용량(`usage`)이 실려 오는가.

    `services/agent_runtime/models/factory.py`의 `ModelFactory._create_openai_compatible()`가
    실제 대화에서 쓰는 것과 같은 요청 모양(`stream_options={"include_usage": True}`)으로
    확인한다. `_verify()`는 **답이 오는가**만 보고 이건 안 본다 — 목록 조회·일반
    호출은 되는데 스트리밍 usage만 안 주는 서버가 있어서(2026-08-21 관측성 작업에서
    실제로 겪음), 등록해 두면 그 팀의 `agent_run.token_in`/`token_out`이 영원히
    `NULL`로 남는데 아무도 그 사실을 모르게 된다.

    여기서 `False`가 나와도 **등록을 막지 않는다** — 답을 주는 능력과 사용량을
    알려주는 능력은 별개라, 후자가 없다고 채팅 기능 자체가 되는 모델을 막을
    이유는 없다. 판단이 안 서면(예외) 지원 안 하는 쪽으로 본다 — 어차피 경고만
    띄우는 용도라 보수적으로 잡아도 위험이 없다.
    """

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url, timeout=25, max_retries=0)
        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
            stream=True,
            stream_options={"include_usage": True},
        )
        return any(getattr(chunk, "usage", None) for chunk in stream)
    except Exception as exc:  # noqa: BLE001 - 판단 못 하면 지원 안 하는 쪽으로 본다
        logger.info("토큰 사용량 지원 확인 실패: %s", type(exc).__name__)
        return False
