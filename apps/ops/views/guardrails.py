"""팀별 외부 가드레일 공급자 등록·연결 확인·삭제.

**팀이 스스로 등록하지 않는다.** 요청을 받으면 운영자가 등록한다 — 커스텀 도구
서버(`views/mcp.py`)·커스텀 모델(`views/models.py`)이 이미 간 길이다. 붙이려면
엔드포인트와 키를 알아야 하는데, 「코딩 없이」를 내세운 제품이 비개발자에게
요구할 일이 아니다.

**권한 범위는 팀이다.** 등록하는 사람만 운영자로 바뀔 뿐, 그 가드레일을 거쳐
도는 것은 그 팀의 대화뿐이다(`guardrail_provider.team_id`).

정본: docs/작업기록/2026-08-20_가드레일_조사와_실측.md §8
"""

import logging

import psycopg
from rest_framework import status
from rest_framework.response import Response

from backend.api_errors import to_response
from backend.db import log_audit
from backend.db.agent_platform import GuardrailProviderRepository
from backend.db.errors import RepositoryError
from services.guardrails.providers import ProviderError, verify as verify_provider

from ..authentication import AdminView
from ..serializers import (
    OpsGuardrailRegisterSerializer,
    OpsGuardrailUpdateSerializer,
    ops_guardrail_row_response,
)

logger = logging.getLogger(__name__)



def _verified_status(*, kind: str, config: dict, credential: dict | None) -> str:
    """저장 직전에 **서버가 직접** 확인한 결과.

    화면이 「연결 확인을 통과했다」고 보내는 것을 믿지 않는다 — 그러면 확인 없이
    CONNECTED 인 행이 생기고, 그 팀의 대화는 안 되는 가드레일을 계속 부른다.

    확인은 저장 직전 한 번뿐이라(등록·수정은 드물다) 비용이 문제되지 않는다.
    대신 **등록 직후 「미확인」으로 남아 다시 눌러야 하던 것**이 없어진다.
    """

    try:
        result = verify_provider(kind=kind, config=config, credential=credential)
    except ProviderError:
        logger.info("가드레일 저장 시 확인 실패: kind=%s", kind)
        return "ERROR"
    return "CONNECTED" if result.ok else "ERROR"


class GuardrailProviderListCreateView(AdminView):
    def get(self, request):
        try:
            rows = GuardrailProviderRepository.list_all()
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response([ops_guardrail_row_response(row) for row in rows])

    def post(self, request):
        serializer = OpsGuardrailRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            config = data.get("config") or {}
            credential = data.get("credential") or None
            row = GuardrailProviderRepository.create(
                team_id=data["team_id"],
                name=data["name"],
                kind=data["kind"],
                config=config,
                credential=credential,
                registered_by=request.user.account_id,
                status=_verified_status(kind=data["kind"], config=config, credential=credential),
                on_failure=data["on_failure"],
            )
            # 남의 팀 대화가 외부 검사기를 거치게 만드는 일이라 반드시 남긴다.
            # **자격증명은 남기지 않는다** — 감사 로그는 사람이 읽는 표다.
            log_audit(
                actor_account_id=request.user.account_id,
                action="OPS_GUARDRAIL_REGISTER",
                target_type="TEAM",
                target_id=data["team_id"],
                payload={
                    "provider_id": row["provider_id"],
                    "name": data["name"],
                    "kind": data["kind"],
                },
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(ops_guardrail_row_response(row), status=status.HTTP_201_CREATED)


class GuardrailProviderProbeView(AdminView):
    """**저장하지 않고** 붙는지만 본다.

    `views/mcp.py` 의 `McpProbeView` 와 같은 자리다 — **검사가 저장보다 먼저다.**
    저장한 뒤에 확인하면 안 되는 것이 DB 에 남고, 그 팀의 대화는 조용히 검사를
    건너뛴다(등록은 됐는데 상태가 ERROR 인 것을 우리 런타임은 부르지 않는다).

    행을 만들지 않으므로 팀도 필요 없다. 실패는 **여기서 끝난다** — 남는 것이
    없으니 고칠 값도 없고, 화면이 이유만 보여주면 된다.
    """

    def post(self, request):
        kind = (request.data.get("kind") or "").strip()
        if kind not in GuardrailProviderRepository.KINDS:
            return Response({"detail": "가드레일 종류를 골라 주세요."}, status=status.HTTP_400_BAD_REQUEST)

        config = request.data.get("config") or {}
        credential = request.data.get("credential") or None
        if not isinstance(config, dict) or (credential is not None and not isinstance(credential, dict)):
            return Response({"detail": "설정 형식이 올바르지 않습니다."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = verify_provider(kind=kind, config=config, credential=credential)
        except ProviderError as exc:
            return Response({"ok": False, "detail": str(exc)})

        if not result.ok:
            # 키가 섞일 수 있는 자리라 예외 문자열을 로그에 그대로 남기지 않는다.
            logger.info("가드레일 저장 전 확인 실패: kind=%s", kind)
        return Response({"ok": result.ok, "detail": result.detail})


class GuardrailProviderDetailView(AdminView):
    def patch(self, request, provider_id):
        serializer = OpsGuardrailUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            config = data.get("config") or {}
            credential = data.get("credential") or None
            # 자격증명을 안 바꾸면 저장된 것으로 확인해야 한다 — 화면은 저장된
            # 값을 되돌려 받지 않으므로 여기서 꺼내 온다.
            probe_credential = credential
            if not data["replace_credential"]:
                probe_credential = GuardrailProviderRepository.credential(provider_id)
            row = GuardrailProviderRepository.update(
                provider_id=provider_id,
                name=data["name"],
                kind=data["kind"],
                config=config,
                credential=credential,
                replace_credential=data["replace_credential"],
                status=_verified_status(
                    kind=data["kind"], config=config, credential=probe_credential
                ),
                on_failure=data["on_failure"],
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)

        # 등록과 같은 이유로 남긴다 — 공급자를 바꾸는 것은 그 팀의 검사가 **다른
        # 곳으로 나가게** 하는 일이라 새로 심는 것과 무게가 같다.
        log_audit(
            actor_account_id=request.user.account_id,
            action="OPS_GUARDRAIL_UPDATE",
            target_type="TEAM",
            target_id=row["team_id"],
            payload={
                "provider_id": provider_id,
                "name": data["name"],
                "kind": data["kind"],
                "credential_replaced": data["replace_credential"],
            },
        )
        return Response(ops_guardrail_row_response(row))

    def delete(self, request, provider_id):
        try:
            row = GuardrailProviderRepository.delete(provider_id=provider_id)
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)

        log_audit(
            actor_account_id=request.user.account_id,
            action="OPS_GUARDRAIL_DELETE",
            target_type="TEAM",
            target_id=row["team_id"],
            payload={"provider_id": provider_id, "name": row["name"], "kind": row["kind"]},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class GuardrailProviderTestView(AdminView):
    """연결 확인 — 무해한 문장 하나를 실제로 보내 본다.

    **자격증명만 형식 검사하지 않는다.** 그러면 「등록은 됐는데 부를 때 401」이
    되고, 그 팀은 운영자가 붙여 줬으니 되는 줄 안다(MCP 의 「연결 확인」과 같은
    판단).

    **실패해도 등록은 남기고 `ERROR` 로 표시한다.** 주소나 키를 고쳐 다시 시도할
    값이고, 상태가 보여야 왜 그 팀의 대화가 검사를 안 거치는지 알 수 있다.
    """

    def post(self, request, provider_id):
        try:
            row = GuardrailProviderRepository.list_all()
            provider = next((item for item in row if item["provider_id"] == provider_id), None)
            if provider is None:
                return Response({"detail": "등록되지 않은 가드레일입니다."}, status=status.HTTP_404_NOT_FOUND)
            credential = GuardrailProviderRepository.credential(provider_id)
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)

        try:
            result = verify_provider(
                kind=provider["kind"], config=provider["config"] or {}, credential=credential
            )
        except ProviderError as exc:
            result = None
            detail = str(exc)
        else:
            detail = result.detail

        ok = bool(result and result.ok)
        if not ok:
            # 키가 섞일 수 있는 자리라 예외 문자열을 로그에 그대로 남기지 않는다.
            logger.warning("가드레일 연결 확인 실패: provider=%s", provider_id)

        try:
            updated = GuardrailProviderRepository.set_status(
                provider_id=provider_id, status="CONNECTED" if ok else "ERROR"
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)

        log_audit(
            actor_account_id=request.user.account_id,
            action="OPS_GUARDRAIL_TEST",
            target_type="TEAM",
            target_id=updated["team_id"],
            payload={"provider_id": provider_id, "status": updated["status"]},
        )
        return Response({**ops_guardrail_row_response(updated), "detail": None if ok else detail})


class TeamActiveGuardrailView(AdminView):
    """그 팀이 **무엇을 쓸지** 정한다.

    **등록 목록(`/ops/guardrails`)이 아니라 팀 상세에서 고른다.** 목록은 전 팀의
    등록물이라 거기서 켜면 「어느 팀의 무엇을 켜는가」가 흐려진다. 기본 채팅 모델이
    이미 같은 길을 갔다(`views/models.py`의 `TeamDefaultModelView`) — 등록은
    `/ops/models`, 고르는 것은 팀 상세다.

    `provider_id` 를 비우면 **아무것도 안 쓴다** — 등록을 지우지 않고 검사만 끈다.
    """

    def put(self, request, team_id):
        provider_id = request.data.get("provider_id")
        if provider_id is not None and not isinstance(provider_id, str):
            return Response({"detail": "가드레일을 골라 주세요."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            row = GuardrailProviderRepository.set_active_for_team(
                team_id=team_id, provider_id=(provider_id or None)
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)

        log_audit(
            actor_account_id=request.user.account_id,
            action="OPS_GUARDRAIL_ACTIVATE",
            target_type="TEAM",
            target_id=team_id,
            payload={"provider_id": provider_id or None, "name": row["name"] if row else None},
        )
        return Response(ops_guardrail_row_response(row) if row else {"provider_id": None})
