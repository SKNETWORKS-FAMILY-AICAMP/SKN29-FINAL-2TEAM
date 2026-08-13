"""팀별 모델 API 부착·회수.

**팀이 스스로 붙이지 않는다.** 회사가 요청하면 운영자가 붙인다(2026-08-13 멘토링).
설정 화면의 등록 폼은 없앴다 — 붙이려면 OpenAI 호환 주소와 키와 모델 식별자를
알아야 하는데, 그건 「코딩 없이」를 내세운 제품이 비개발자에게 요구할 일이 아니다.
실제로 Google 호환 주소는 AI Studio 화면에 없어서 문서를 뒤져야 나왔다.

**권한 범위는 여전히 팀이다.** 붙이는 사람만 운영자로 바뀔 뿐, 그 모델을 고르고
실행에 쓰는 것은 그 팀뿐이다(`CustomModelRepository._rows` 가 `user_account.team_id`
로 거른다). 조직 단위로 넓히는 것은 하지 않기로 했다(2026-08-13 PM 결정).
"""

import logging

import psycopg
from rest_framework import status
from rest_framework.response import Response

from backend.api_errors import to_response
from backend.db import log_audit
from backend.db.agent_platform import CustomModelRepository
from backend.db.errors import RepositoryError

from ..authentication import AdminView
from ..serializers import OpsModelAttachSerializer, ops_model_row_response

logger = logging.getLogger(__name__)


class ModelListCreateView(AdminView):
    def get(self, request):
        try:
            rows = CustomModelRepository.list_all()
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response([ops_model_row_response(row) for row in rows])

    def post(self, request):
        serializer = OpsModelAttachSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # **같은 팀에 같은 이름을 두 번 두지 않는다.** 경로가 모델 이름 하나로
        # 정해지므로(`for_model`), 겹치면 실행은 먼저 붙인 것으로 고정되는데
        # 목록에는 둘로 보인다 — 어느 것으로 도는지 아무도 모르게 된다.
        try:
            if data["model"] in CustomModelRepository.models_for_team(data["team_id"]):
                return Response(
                    {"detail": f"{data['model']} 은 이 팀에 이미 붙어 있습니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)

        # **붙이기 전에 한 번 써 본다.** 안 되는 것을 붙여 두면 그 팀의 대화가
        # 조용히 실패하고, 팀은 운영자가 붙여 줬으니 되는 줄 안다.
        error = _verify(data["api_key"], data["base_url"], data["model"])
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        try:
            CustomModelRepository.add_for_team(
                team_id=data["team_id"],
                label=data["label"],
                base_url=data["base_url"],
                api_key=data["api_key"],
                model=data["model"],
                attached_by=request.user.account_id,
            )
            # 남의 팀에 외부 호출 경로를 심는 일이라 반드시 기록에 남는다.
            # **키는 남기지 않는다** — 감사 로그는 나중에 사람이 읽는 표다.
            log_audit(
                actor_account_id=request.user.account_id,
                action="OPS_MODEL_ATTACH",
                target_type="TEAM",
                target_id=data["team_id"],
                payload={"model": data["model"], "label": data["label"], "base_url": data["base_url"]},
            )
            rows = CustomModelRepository.list_all()
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response([ops_model_row_response(row) for row in rows], status=status.HTTP_201_CREATED)


class ModelDetailView(AdminView):
    def delete(self, request, conn_id):
        try:
            CustomModelRepository.remove_by_conn_id(conn_id)
            log_audit(
                actor_account_id=request.user.account_id,
                action="OPS_MODEL_DETACH",
                target_type="CONNECTOR_CONN",
                target_id=conn_id,
            )
            rows = CustomModelRepository.list_all()
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response([ops_model_row_response(row) for row in rows])


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
        logger.warning("모델 부착 확인 실패: %s", type(exc).__name__)
        return "이 주소와 모델로 답을 받지 못했습니다. 주소·키·모델 이름을 확인해 주세요."
    return None
