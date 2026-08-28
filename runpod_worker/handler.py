from __future__ import annotations

import os

from dotenv import load_dotenv
import runpod

from pipeline import PipelineConfigurationError, embed_documents, embed_queries, process_document


load_dotenv()


def handler(job: dict) -> dict:
    payload = job.get("input")
    if not isinstance(payload, dict):
        raise ValueError("RunPod job.input 객체가 필요합니다.")
    action = payload.get("action")
    if action == "process_document":
        return process_document(payload)
    if action == "embed_queries":
        return embed_queries(payload)
    if action == "embed_documents":
        return embed_documents(payload)
    raise ValueError(f"지원하지 않는 Worker action입니다: {action}")


if __name__ == "__main__":
    # Validate non-secret configuration before accepting a job. Secrets are
    # checked when the model/download boundary is used so they never get logged.
    if os.getenv("EMBEDDING_DEVICE") != "cuda":
        raise PipelineConfigurationError("EMBEDDING_DEVICE는 cuda여야 합니다.")
    runpod.serverless.start({"handler": handler})
