from io import BytesIO

from django.conf import settings
from django.core import signing
from django.http import FileResponse
import psycopg
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import BearerTokenAuthentication
from apps.connectors.clients import download_drive_file, list_drive_files
from apps.connectors.oauth import OAuthError
from backend.services.storage import build_key
from backend.services.storage import save as save_document
from backend.services.storage import exists as document_exists
from backend.services.storage import load as load_document
from backend.db import (
    AnalysisRunRepository,
    DocumentRepository,
    ProjectRepository,
    ProjectSourceRepository,
    database_status,
)
from backend.db.errors import (
    PermissionDenied,
    RecordNotFound,
    ReferenceNotFound,
    RepositoryError,
)
from backend.db.document_pipeline import PipelineDocumentRepository
from services.document_pipeline.errors import (
    DocumentPipelineError,
    PipelineConfigurationError,
    RunPodRequestError,
)
from services.document_pipeline.runpod_client import job_status, submit_document_job
from services.document_pipeline.signing import read_download_token, signed_download_url
from services.task_extraction import extract_tasks

from .serializers import (
    AssignmentRunCreateSerializer,
    DocumentRoleSaveSerializer,
    ProjectCreateSerializer,
    ProjectSourceReplaceSerializer,
    TaskExtractionCreateSerializer,
    assignment_run_response,
    document_response,
    project_response,
    project_source_response,
)


def _repository_error_response(exc: Exception) -> Response:
    if isinstance(exc, RecordNotFound):
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, PermissionDenied):
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    if isinstance(exc, ReferenceNotFound):
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    if isinstance(exc, RepositoryError):
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(
        {"detail": "데이터베이스 요청을 처리할 수 없습니다.", "error": exc.__class__.__name__},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


class AuthenticatedAPIView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]


def _pipeline_error_response(exc: Exception) -> Response:
    if isinstance(exc, PipelineConfigurationError):
        return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    if isinstance(exc, RunPodRequestError):
        return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
    if isinstance(exc, DocumentPipelineError):
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    return Response(
        {"detail": str(exc) or exc.__class__.__name__},
        status=status.HTTP_409_CONFLICT,
    )


class HealthAPIView(APIView):
    def get(self, request):
        return Response(
            {
                "status": "ok",
                "service": "ai-project-operation-copilot",
                "database": database_status(),
            }
        )


class ProjectListCreateAPIView(AuthenticatedAPIView):
    """내가 소유한 프로젝트. 온보딩은 여기서 DRAFT를 찾거나 만든다."""

    def get(self, request):
        try:
            rows = ProjectRepository.list_for_owner(request.user.account_id)
        except psycopg.Error as exc:
            return _repository_error_response(exc)
        return Response([project_response(row) for row in rows])

    def post(self, request):
        serializer = ProjectCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            row = ProjectRepository.create(
                **serializer.validated_data,
                owner_account_id=request.user.account_id,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(project_response(row), status=status.HTTP_201_CREATED)


class ProjectDetailAPIView(AuthenticatedAPIView):
    def get(self, request, project_id):
        try:
            row = ProjectRepository.get(project_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(project_response(row))


class ProjectSourceAPIView(AuthenticatedAPIView):
    """이 프로젝트가 읽을 Drive 폴더·Jira 프로젝트(`proj_source`)."""

    def get(self, request, project_id):
        try:
            rows = ProjectSourceRepository.list_for_project(
                proj_id=project_id,
                account_id=request.user.account_id,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response([project_source_response(row) for row in rows])

    def put(self, request, project_id):
        serializer = ProjectSourceReplaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            rows = ProjectSourceRepository.replace(
                proj_id=project_id,
                account_id=request.user.account_id,
                **serializer.validated_data,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response([project_source_response(row) for row in rows])


class ProjectDocumentAPIView(AuthenticatedAPIView):
    """역할 지정 화면의 저장. 폴더 역할과 그것을 물려받은 `doc` 행을 함께 쓴다."""

    def get(self, request, project_id):
        try:
            rows = DocumentRepository.list_for_project(
                proj_id=project_id,
                account_id=request.user.account_id,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response([document_response(row) for row in rows])

    def put(self, request, project_id):
        serializer = DocumentRoleSaveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        folder_roles = serializer.validated_data["folder_roles"]
        file_roles = serializer.validated_data["file_roles"]
        account_id = request.user.account_id

        try:
            sources = ProjectSourceRepository.list_for_project(proj_id=project_id, account_id=account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        # 파일 목록은 Drive에서 직접 읽는다. 파싱할 수 없는 형식은 등록하지 않는다.
        documents = []
        for source in sources:
            if source["source_type"] != ProjectSourceRepository.DRIVE_FOLDER:
                continue
            folder_id = source["external_source_id"]
            try:
                # 폴더를 저장할 때 정한 탐색 깊이를 그대로 쓴다.
                files = list_drive_files(
                    account_id=account_id,
                    parent_id=folder_id,
                    max_depth=source["max_depth"],
                )
            except OAuthError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
            except (RepositoryError, psycopg.Error) as exc:
                return _repository_error_response(exc)

            inherited = folder_roles.get(folder_id)
            for item in files:
                if not item["supported"]:
                    continue
                doc_role = file_roles.get(item["file_id"]) or inherited
                if doc_role is None:
                    continue
                documents.append(
                    {
                        "src_file_id": item["file_id"],
                        "file_name": item["name"],
                        "mime_type": item["mime_type"],
                        "doc_role": doc_role,
                        "src_modified_at": item["modified_at"],
                    }
                )

        try:
            rows = DocumentRepository.save_drive_documents(
                proj_id=project_id,
                account_id=account_id,
                folder_roles=folder_roles,
                documents=documents,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response([document_response(row) for row in rows])


class ProjectDocumentDownloadAPIView(AuthenticatedAPIView):
    """선택된 문서의 원문을 Drive에서 받아 문서 저장소에 넣는다.

    파싱은 이 저장소를 입력으로 삼는다. 파싱이 Drive를 직접 읽지 않는 이유는,
    사용자 OAuth 토큰이 파싱 쪽으로 넘어가면 안 되기 때문이다 — 토큰 하나로
    그 사람의 드라이브 전체를 읽을 수 있다.

    한 건이 실패해도 나머지는 계속 받는다. Drive에서 지워졌거나 권한이 빠진
    문서 하나 때문에 전체가 멈추면, 무엇이 문제인지 알 수 없는 채로 아무것도
    안 받은 상태가 된다.
    """

    def post(self, request, project_id):
        account_id = request.user.account_id
        force = request.data.get("force") is True

        try:
            targets = DocumentRepository.list_pending_download(
                proj_id=project_id,
                account_id=account_id,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        downloaded, skipped, failed = [], [], []
        for target in targets:
            if target["storage_key"] and not force:
                skipped.append(target["file_name"])
                continue

            try:
                fetched = download_drive_file(
                    account_id=account_id,
                    file_id=target["src_file_id"],
                    mime_type=target["mime_type"],
                )
            except OAuthError as exc:
                failed.append({"file_name": target["file_name"], "detail": str(exc)})
                continue

            key = build_key(
                proj_id=project_id,
                doc_id=target["doc_id"],
                mime_type=fetched["mime_type"],
            )
            try:
                # 파일을 먼저 쓰고 DB에 기록한다. 반대 순서면 "DB에는 있는데 파일이
                # 없는" 상태가 생기고, 파싱이 그걸 읽다가 죽는다.
                content_hash = save_document(key, fetched["content"])
                DocumentRepository.mark_stored(
                    doc_id=target["doc_id"],
                    storage_key=key,
                    content_hash=content_hash,
                    revision=fetched["revision"],
                )
            except OSError as exc:
                failed.append({"file_name": target["file_name"], "detail": f"저장 실패: {exc}"})
                continue
            except (RepositoryError, psycopg.Error) as exc:
                return _repository_error_response(exc)

            downloaded.append({"file_name": target["file_name"], "bytes": len(fetched["content"])})

        return Response(
            {
                "downloaded": downloaded,
                "skipped": skipped,
                "failed": failed,
            }
        )


class ProjectAnalysisRunAPIView(AuthenticatedAPIView):
    """현재 `assign_run` 테이블에 배정 실행을 생성한다."""

    def post(self, request, project_id):
        serializer = AssignmentRunCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            row = AnalysisRunRepository.create(
                proj_id=project_id,
                **serializer.validated_data,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        row["proj_id"] = project_id
        return Response(assignment_run_response(row), status=status.HTTP_201_CREATED)


class AnalysisRunDetailAPIView(AuthenticatedAPIView):
    def get(self, request, run_id):
        try:
            row = AnalysisRunRepository.get(run_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(assignment_run_response(row))


class DocumentProcessingRunAPIView(AuthenticatedAPIView):
    """Submit and poll one RunPod Serverless document-processing job."""

    def post(self, request, project_id, doc_id):
        try:
            document = PipelineDocumentRepository.get_for_processing(
                proj_id=project_id,
                doc_id=doc_id,
                account_id=request.user.account_id,
            )
            if not document_exists(document["storage_key"]):
                return Response(
                    {"detail": "로컬 문서 저장소에 원문 파일이 없습니다."},
                    status=status.HTTP_409_CONFLICT,
                )
            source_url = signed_download_url(
                project_id=project_id,
                doc_id=doc_id,
                revision=document["cur_revision"],
            )
            result = submit_document_job(
                {
                    "doc_id": doc_id,
                    "revision": document["cur_revision"],
                    "mime_type": document["mime_type"],
                    "source_url": source_url,
                    "max_tokens": settings.CHUNKING_MAX_TOKENS,
                    "merge_peers": settings.CHUNKING_MERGE_PEERS,
                }
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        except (ValueError, OSError, DocumentPipelineError) as exc:
            return _pipeline_error_response(exc)
        return Response(
            {"job_id": result["id"], "status": result.get("status", "IN_QUEUE")},
            status=status.HTTP_202_ACCEPTED,
        )

    def get(self, request, project_id, doc_id, job_id):
        try:
            document = PipelineDocumentRepository.get_for_processing(
                proj_id=project_id,
                doc_id=doc_id,
                account_id=request.user.account_id,
            )
            result = job_status(job_id)
            runpod_status = result.get("status")
            response_payload = {"job_id": job_id, "status": runpod_status}
            if runpod_status == "COMPLETED":
                output = result.get("output")
                if not isinstance(output, dict):
                    raise ValueError("완료된 RunPod 작업에 output 객체가 없습니다.")
                response_payload["ingested"] = PipelineDocumentRepository.ingest(
                    expected_doc=document,
                    result=output,
                )
            elif runpod_status in {"FAILED", "CANCELLED", "TIMED_OUT"}:
                response_payload["error"] = result.get("error") or "RunPod 문서 처리 실패"
            return Response(response_payload)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        except (ValueError, OSError, DocumentPipelineError) as exc:
            return _pipeline_error_response(exc)


class RunPodDocumentDownloadAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, doc_id):
        token = request.query_params.get("token", "")
        try:
            payload = read_download_token(token)
            if payload["doc_id"] != doc_id:
                raise signing.BadSignature("URL과 서명 문서 ID가 다릅니다.")
            document = PipelineDocumentRepository.get_signed_download(
                proj_id=payload["project_id"],
                doc_id=doc_id,
                revision=payload["revision"],
            )
            if not document_exists(document["storage_key"]):
                raise RecordNotFound("로컬 저장소에 문서 원문이 없습니다.")
            stream = BytesIO(load_document(document["storage_key"]))
        except signing.SignatureExpired:
            return Response({"detail": "문서 다운로드 서명이 만료되었습니다."}, status=403)
        except signing.BadSignature:
            return Response({"detail": "문서 다운로드 서명이 올바르지 않습니다."}, status=403)
        except (RecordNotFound, PermissionDenied):
            return Response({"detail": "문서를 찾을 수 없습니다."}, status=404)
        return FileResponse(
            stream,
            content_type=document["mime_type"] or "application/octet-stream",
            as_attachment=True,
            filename=document["file_name"] or f"{doc_id}.bin",
        )


class TaskExtractionRunAPIView(AuthenticatedAPIView):
    def post(self, request, project_id):
        serializer = TaskExtractionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            documents = PipelineDocumentRepository.list_ready_for_analysis(
                proj_id=project_id,
                account_id=request.user.account_id,
            )
            selected_id = serializer.validated_data["primary_document_id"]
            primary = next((d for d in documents if d["doc_id"] == selected_id), None)
            if primary is None:
                return Response(
                    {"detail": "선택한 문서가 이 프로젝트의 분석 대상이 아닙니다."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if not primary["search_ready"]:
                return Response(
                    {"detail": "문서가 아직 파싱·청킹·임베딩되지 않았습니다."},
                    status=status.HTTP_409_CONFLICT,
                )
            ready_ids = [d["doc_id"] for d in documents if d["search_ready"]]
            result = extract_tasks(
                project_id=project_id,
                primary_document=primary,
                document_ids=ready_ids,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        except Exception as exc:
            return _pipeline_error_response(exc)
        return Response(result, status=status.HTTP_201_CREATED)
