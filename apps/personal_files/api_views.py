"""「내 파일」 — 사용자가 올린 개인 소유 문서 (M④ · 2026-08-18 멘토링).

**커넥터 문서와 갈리는 것은 「누구 것이냐」다**(8/18 PM). 팀 문서는 폴더를
정하면 시스템이 알아서 받아들이고(`services/document_intake`), 여기 올린 파일은
내 것이라 **내가 켜고 끈다.**

세 가지가 커넥터 문서와 다르다.

- **원본이 우리뿐이다.** Drive 에서 받아 온 것이 아니라 되받을 곳이 없다.
  그래서 지우면 되살릴 수 없고, `deleted` 표시만 남기는 커넥터 방식과 다르게
  행·색인·원문을 함께 지운다.
- **승격 경로를 그대로 탄다.** 8/15 결정대로 파싱·임베딩은 **검색이 그 문서를
  필요로 할 때** 돈다. 워커는 Drive 가 아니라 **우리 저장소**에서 받아 가므로
  (`RunPodDocumentDownloadAPIView` 가 `storage_key` 를 읽어 준다) 올린 파일도
  커넥터 문서와 똑같이 승격된다.
- **뜻 없는 칸이 있다.** `src_file_id`·`access_revoked` 같은 것은 영영 NULL 이다.
  없는 것이 정상이다.
"""

import logging
import threading

import psycopg
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import BearerTokenAuthentication
from backend.db.document_pipeline import PersonalDocumentRepository
from backend.db.errors import PermissionDenied, RecordNotFound, RepositoryError
from backend.db.repositories import DocumentRepository
from backend.services import storage

from .serializers import personal_file_response

logger = logging.getLogger(__name__)

#: 한 파일의 상한. **파싱하는 쪽이 정하는 값이다** — 저장은 되는데 파싱이 조용히
#: 죽는 크기를 열어 두면 안 된다. RunPod 워커의 실측 상한을 확인하기 전까지는
#: 보수적으로 잡는다(아바타 2MB 와는 다른 값이라 여기서 따로 정한다).
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

#: PDF·DOCX 는 본문까지, txt·md 는 요약까지 쓸 수 있다(`_UPLOAD_TYPES` 주석).
ACCEPTED = "PDF · Word(docx) · 텍스트(txt·md)"


def _error_response(exc: Exception) -> Response:
    if isinstance(exc, RecordNotFound):
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, PermissionDenied):
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    if isinstance(exc, RepositoryError):
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(
        {"detail": "데이터베이스 요청을 처리할 수 없습니다.", "error": exc.__class__.__name__},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


class AuthenticatedAPIView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]


class PersonalFileListAPIView(AuthenticatedAPIView):
    def get(self, request):
        try:
            rows = PersonalDocumentRepository.list_for_account(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _error_response(exc)
        return Response([personal_file_response(row) for row in rows])

    def post(self, request):
        """올린다. **아바타 업로드와 같은 순서다**(`apps/accounts/api_views.py`) —
        크기를 먼저 보고, 형식을 우리가 판정하고, 파일을 먼저 쓰고 기록을 나중에.

        기록이 먼저면 「DB 에는 있는데 파일이 없는」 상태가 생기고 파싱이 그걸
        읽다가 죽는다. 반대로 파일만 남는 것은 다음 업로드가 덮어쓴다.
        """

        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "파일을 첨부해 주세요."}, status=status.HTTP_400_BAD_REQUEST)
        if upload.size > MAX_UPLOAD_BYTES:
            return Response(
                {"detail": f"파일은 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB 이하여야 합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = upload.read()
        # 브라우저가 보내는 Content-Type 은 믿지 않는다. 확장자로 정하고,
        # 시그니처가 있는 형식은 바이트로 한 번 더 본다(`upload_mime_type` 주석).
        mime_type = storage.upload_mime_type(upload.name, data)
        if mime_type is None:
            return Response(
                {"detail": f"{ACCEPTED} 만 올릴 수 있습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        account_id = request.user.account_id
        try:
            doc_id = PersonalDocumentRepository.create(
                account_id=account_id, file_name=upload.name, mime_type=mime_type
            )
            key = storage.build_personal_key(
                account_id=account_id, doc_id=doc_id, mime_type=mime_type
            )
            content_hash = storage.save(key, data)
            # 올린 파일에는 원천 리비전이 없다. 내용 해시를 그 자리에 쓴다 —
            # 파싱 경로(`signed_download_url`)가 doc_id 와 함께 서명하는 값이라
            # 비워 둘 수 없고, 내용이 바뀌면 달라져야 하는 성질도 같다.
            DocumentRepository.mark_stored(
                doc_id=doc_id,
                storage_key=key,
                content_hash=content_hash,
                revision=content_hash.removeprefix("sha256:")[:16],
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _error_response(exc)
        except OSError as exc:
            logger.exception("내 파일 저장 실패: %s", upload.name)
            return Response(
                {"detail": "파일을 저장하지 못했습니다.", "error": exc.__class__.__name__},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        _start_processing(account_id=account_id, doc_id=doc_id)
        return Response(
            {"doc_id": doc_id, "file_name": upload.name, "processing": True},
            status=status.HTTP_201_CREATED,
        )


class SharedFileListAPIView(AuthenticatedAPIView):
    """팀원이 공유한 파일. **내가 올린 것은 안 나온다** — 「내 파일」에 이미 있고,
    두 목록에 같은 줄이 뜨면 어느 쪽에서 지워야 하는지 모른다."""

    def get(self, request):
        try:
            rows = PersonalDocumentRepository.list_shared_with_me(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _error_response(exc)
        return Response([personal_file_response(row) for row in rows])


class PersonalFileReindexAPIView(AuthenticatedAPIView):
    """색인을 **다시 시킨다.** 팀 문서의 같은 이름 화면과 짝이다
    (`apps/projects/api_views.py` 의 `TeamDocumentReindexAPIView`).

    올린 파일에는 이 길이 없었다. 실패하면 지우고 다시 올리는 수밖에 없었는데,
    같은 파일을 같은 파서로 다시 읽히는 일에 파일을 지울 이유가 없다 — 실패는
    대개 그때 워커가 못 돌았다는 뜻이라 다시 눌러 보는 것이 맞는 조치다.

    **응답을 붙잡지 않는다.** 승격은 워커를 기다려 한 건에 100초 남짓이다.
    시작할 때 `RUNNING` 을, 끝날 때 결과를 적으므로 화면은 그 칸을 폴링한다.
    """

    def post(self, request, doc_id):
        account_id = request.user.account_id
        try:
            # **내 파일인지 여기서 본다.** 뒷작업으로 던지고 나면 남의 문서를
            # 돌리고 있어도 응답은 이미 202 로 나간 뒤다.
            rows = PersonalDocumentRepository.list_for_account(account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _error_response(exc)

        target = next((row for row in rows if row["doc_id"] == doc_id), None)
        if target is None:
            return Response(
                {"detail": "내가 올린 파일이 아닙니다."}, status=status.HTTP_404_NOT_FOUND
            )
        if not target["storage_key"]:
            # 원문이 없으면 색인이 시작조차 못 한다. 던져 놓고 실패시키면
            # 「돌고 있다」로 보였다가 조용히 실패하므로 여기서 끊는다.
            return Response(
                {"detail": "아직 파일을 받지 못했습니다."}, status=status.HTTP_409_CONFLICT
            )

        _start_processing(account_id=account_id, doc_id=doc_id)
        return Response({"doc_id": doc_id, "started": True}, status=status.HTTP_202_ACCEPTED)


class PersonalFileDetailAPIView(AuthenticatedAPIView):
    def patch(self, request, doc_id):
        """toggle 둘. 켜고 끄는 것뿐이라 다른 값은 안 받는다.

        **`search_enabled` 와 `shared` 는 다른 값이다.** 앞은 「내 검색에 쓴다」,
        뒤는 「팀이 봐도 된다」다 — 내 검색에서 빼 두고 팀에는 공유하는 것도,
        그 반대도 말이 된다.
        """

        enabled = request.data.get("search_enabled")
        shared = request.data.get("shared")
        if enabled is None and shared is None:
            return Response(
                {"detail": "search_enabled 또는 shared 가 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if (enabled is not None and not isinstance(enabled, bool)) or (
            shared is not None and not isinstance(shared, bool)
        ):
            return Response(
                {"detail": "search_enabled·shared 는 true 또는 false 여야 합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        account_id = request.user.account_id
        try:
            if enabled is not None:
                PersonalDocumentRepository.set_search_enabled(
                    doc_id=doc_id, account_id=account_id, enabled=enabled
                )
            if shared is not None:
                PersonalDocumentRepository.set_shared(
                    doc_id=doc_id, account_id=account_id, shared=shared
                )
        except (RepositoryError, psycopg.Error) as exc:
            return _error_response(exc)
        return Response({"doc_id": doc_id, "search_enabled": enabled, "shared": shared})

    def delete(self, request, doc_id):
        """**되살릴 수 없다.** 원본이 우리뿐이라 지우면 그것으로 끝이다 —
        확인은 화면이 받는다."""

        try:
            key = PersonalDocumentRepository.delete(
                doc_id=doc_id, account_id=request.user.account_id
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _error_response(exc)

        if key:
            try:
                storage.remove(key)
            except OSError:
                # 행은 이미 지웠다. 원문만 남는 것은 아무도 못 찾는 파일 하나이지
                # 화면이 깨지는 상태는 아니라, 여기서 실패를 되돌리지 않는다.
                logger.warning("내 파일 원문 삭제 실패: %s", key)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _start_processing(*, account_id: str, doc_id: str) -> None:
    """올린 파일을 **본문 색인까지** 뒤에서 올린다.

    한동안 여기서 요약만 만들고 청크 파싱·임베딩은 미뤘다(2026-08-15 결정 ·
    8/18 PM 확인). 검색이 요약으로 후보를 좁힌 뒤 그 문서에만 돌린다는 전제였는데,
    **그 좁히기 자체를 없앴다**(2026-08-24) — 커넥터 문서가 전부 색인되는 것과
    같은 이유다. 올린 파일도 같은 길을 간다.

    워커는 Drive 가 아니라 **우리 저장소**에서 받아 가므로 올린 파일도 똑같이
    승격된다.

    **응답을 붙잡아 두지 않는다.** 색인은 문서당 100초 남짓이다. 진행은 목록의
    상태(`index_status`)가 말하고, 실패하면 그 사유(`index_detail`)까지 남는다.
    폴더 저장이 문서 수집을 뒤에서 돌리는 것과 같은 방식이다
    (`apps/projects/api_views.py` 의 `_start_document_intake`).
    """

    def run() -> None:
        try:
            from services.document_intake import promote_to_searchable

            promote_to_searchable(account_id=account_id, doc_id=doc_id)
        except Exception:  # noqa: BLE001 - 뒤에서 도는 일이라 무엇이든 로그로 남긴다
            logger.exception("내 파일 색인 실패: %s", doc_id)
            # **로그만 남기면 문서가 `RUNNING` 에 갇힌다.** 승격은 시작하면서
            # 먼저 `RUNNING` 을 적는데, 워커에 넘기기도 전에 터지면(예: 제출이
            # 네트워크에서 실패) 결과를 적는 자리까지 못 간다. 그러면 화면은
            # **영원히 「읽는 중」**이다 — 올린 사람은 업로드가 안 된 것으로 읽는다.
            #
            # 팀 문서는 다음 전량 색인이 주워 가지만(`list_pending_index` 가
            # `RUNNING` 을 일부러 남긴다) **올린 파일은 `team_id` 가 없어서 그
            # 목록에 영영 안 걸린다.** 여기서 끝을 내야 한다.
            try:
                PersonalDocumentRepository.set_index_status(
                    doc_id=doc_id,
                    status="FAILED",
                    detail="문서를 읽지 못했습니다. 다시 올려 주세요.",
                )
            except Exception:  # noqa: BLE001 - 이것마저 실패하면 남길 곳이 없다
                logger.exception("내 파일 실패 표시 실패: %s", doc_id)

    threading.Thread(target=run, daemon=True).start()
