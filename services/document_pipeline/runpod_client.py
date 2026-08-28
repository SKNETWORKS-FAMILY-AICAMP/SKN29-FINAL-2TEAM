from __future__ import annotations

import time
from typing import Any

from django.conf import settings
import requests

from .errors import PipelineConfigurationError, RunPodRequestError


TERMINAL_STATUSES = {"COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"}


def _configuration() -> tuple[str, dict[str, str]]:
    missing = [
        name
        for name, value in (
            ("RUNPOD_API_KEY", settings.RUNPOD_API_KEY),
            ("RUNPOD_ENDPOINT_ID", settings.RUNPOD_ENDPOINT_ID),
        )
        if not str(value).strip()
    ]
    if missing:
        raise PipelineConfigurationError(f"필수 RunPod 설정이 없습니다: {', '.join(missing)}")
    base = f"https://api.runpod.ai/v2/{settings.RUNPOD_ENDPOINT_ID}"
    return base, {"Authorization": f"Bearer {settings.RUNPOD_API_KEY}"}


def _json_response(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise RunPodRequestError("RunPod가 JSON이 아닌 응답을 반환했습니다.") from exc
    if not response.ok:
        raise RunPodRequestError(
            f"RunPod 요청 실패({response.status_code}): {payload.get('error') or payload}"
        )
    if not isinstance(payload, dict):
        raise RunPodRequestError("RunPod 응답은 JSON 객체여야 합니다.")
    return payload


def submit_document_job(payload: dict[str, Any]) -> dict[str, Any]:
    base, headers = _configuration()
    body = {
        "input": {"action": "process_document", **payload},
        "policy": {
            "ttl": settings.RUNPOD_JOB_TTL_MS,
            "executionTimeout": settings.RUNPOD_EXECUTION_TIMEOUT_MS,
        },
    }
    try:
        response = requests.post(f"{base}/run", json=body, headers=headers, timeout=(10, 30))
    except requests.RequestException as exc:
        raise RunPodRequestError(f"RunPod 작업 요청에 실패했습니다: {exc}") from exc
    result = _json_response(response)
    if not result.get("id"):
        raise RunPodRequestError("RunPod 응답에 job id가 없습니다.")
    return result


def job_status(job_id: str) -> dict[str, Any]:
    if not job_id or "/" in job_id or "\\" in job_id:
        raise RunPodRequestError("올바르지 않은 RunPod job id입니다.")
    base, headers = _configuration()
    try:
        response = requests.get(f"{base}/status/{job_id}", headers=headers, timeout=(10, 30))
    except requests.RequestException as exc:
        raise RunPodRequestError(f"RunPod 상태 조회에 실패했습니다: {exc}") from exc
    return _json_response(response)


def _await_job(job_id: str) -> dict[str, Any]:
    """작업이 끝날 때까지 상태를 묻는다.

    기다리는 대상은 대부분 워커 콜드 스타트다. 이미지 pull 과 모델 다운로드에
    몇 분이 걸리므로 기본 한도를 넉넉히 둔다. 그래도 안 끝나면 마지막 상태를
    그대로 돌려주고, 판단은 호출자가 한다.
    """

    deadline = time.monotonic() + settings.RUNPOD_EMBED_WAIT_SECONDS
    payload: dict[str, Any] = {"status": "IN_QUEUE", "id": job_id}
    while time.monotonic() < deadline:
        time.sleep(3)
        payload = job_status(job_id)
        if payload.get("status") in TERMINAL_STATUSES:
            return payload
    return payload


def embed_queries(texts: list[str]) -> list[list[float]]:
    base, headers = _configuration()
    if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError("검색 임베딩에는 비어 있지 않은 문자열이 필요합니다.")
    try:
        response = requests.post(
            f"{base}/runsync",
            json={
                "input": {"action": "embed_queries", "texts": texts},
                "policy": {"executionTimeout": settings.RUNPOD_EXECUTION_TIMEOUT_MS},
            },
            headers=headers,
            timeout=(10, 300),
        )
    except requests.RequestException as exc:
        raise RunPodRequestError(f"RunPod 검색 임베딩 요청에 실패했습니다: {exc}") from exc
    payload = _json_response(response)

    # `/runsync` 는 자기 대기 창이 끝나면 **아직 큐에 있어도** 그대로 돌려준다.
    # 워커가 0으로 줄어 있으면 콜드 스타트에 몇 분이 걸리는데, 그것을 실패로
    # 읽어서 이미 돈을 쓴 검색어 생성까지 버려졌다(2026-08-05). 끝날 때까지
    # job id 로 이어서 묻는다 — 문서 처리 경로가 하는 것과 같다.

    if payload.get("status") not in TERMINAL_STATUSES and payload.get("id"):
        payload = _await_job(payload["id"])

    if payload.get("status") != "COMPLETED":
        raise RunPodRequestError(f"검색 임베딩 작업이 완료되지 않았습니다: {payload.get('status')}")
    output = payload.get("output")
    vectors = output.get("embeddings") if isinstance(output, dict) else None
    if not isinstance(vectors, list) or len(vectors) != len(texts):
        raise RunPodRequestError("검색 임베딩 결과 개수가 요청과 다릅니다.")
    if any(not isinstance(v, list) or len(v) != 768 for v in vectors):
        raise RunPodRequestError("검색 임베딩은 모두 768차원이어야 합니다.")
    return vectors
