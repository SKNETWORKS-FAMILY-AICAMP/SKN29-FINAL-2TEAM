"""Fail-closed adapter from an in-memory DoclingDocument to reading-order policy.

This file is intentionally thin.  The validated policy implementation remains
in ``run_reading_order_postprocess.py``; the adapter only bridges the RunPod
worker's in-memory document to that JSON-oriented implementation.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Any

CODE_ROOT = Path(__file__).resolve().parent
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from run_reading_order_postprocess import POLICIES, run_postprocess


def _validate_docling_document(value: dict[str, Any]) -> Any:
    # Lazy import keeps detector/unit tests lightweight.  The production
    # Worker already has docling-core through its pinned Docling dependency.
    from docling_core.types.doc import DoclingDocument

    return DoclingDocument.model_validate(value)


def _document_dict(document: Any) -> dict[str, Any]:
    if hasattr(document, "model_dump"):
        return document.model_dump(mode="json", exclude_none=True)
    if hasattr(document, "export_json_dict"):
        return document.export_json_dict()
    if isinstance(document, dict):
        return document
    raise TypeError(f"unsupported Docling document type: {type(document).__name__}")


def postprocess_docling_document(
    document: Any,
    policy: str = "validated-local-v1",
) -> tuple[Any, dict[str, Any]]:
    """Return ``(document, audit)`` under a fail-closed two-outcome contract.

    Any adapter, policy, apply, or final Docling schema failure preserves the
    original object and is surfaced in the returned audit.  The caller can
    therefore keep the worker pipeline running without silently accepting an
    invalid tree.  Use ``shadow`` for the first integration smoke test and
    ``validated-local-v1`` only after the unchanged path has been verified.
    """

    if policy not in POLICIES:
        raise ValueError(f"unsupported policy: {policy}")

    try:
        source = _document_dict(document)
    except (TypeError, ValueError) as exc:
        return document, {
            "schema_version": "reading-order-worker-adapter.v1",
            "outcome": "PRESERVED",
            "policy": policy,
            "applied_count": 0,
            "failure_reason": f"adapter_input_failed: {exc}",
        }

    try:
        with TemporaryDirectory(prefix="reading_order_") as temp_dir:
            source_path = Path(temp_dir) / "document.json"
            source_path.write_text(
                json.dumps(source, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            corrected, audit = run_postprocess(source_path, policy)
        if audit.get("failure_reason") is not None:
            return document, audit
        if audit.get("outcome") != "CORRECTED":
            return document, audit
        validated = _validate_docling_document(corrected)
        audit["docling_core_schema_validation"] = "PASS"
        return validated, audit
    # This is the Worker boundary: an unexpected postprocessor failure must
    # never discard an otherwise valid Docling result.  Exception is caught
    # here deliberately (not inside detector logic) so the original document
    # is preserved while the exact failure remains visible in the audit.
    except Exception as exc:
        return document, {
            "schema_version": "reading-order-worker-adapter.v1",
            "outcome": "PRESERVED",
            "policy": policy,
            "applied_count": 0,
            "failure_reason": f"adapter_execution_failed: {exc}",
        }
