"""Gold-label metrics for reading-order candidates.

This module evaluates detector output only.  It never mutates a Docling document
and does not inspect or modify heading labels or levels.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


CONFIRMED = "CONFIRMED"
ORDER_ERROR = "ORDER_ERROR"
NORMAL_PRESERVE = "NORMAL_PRESERVE"
STRUCTURAL_BOUNDARY = "STRUCTURAL_BOUNDARY"
AMBIGUOUS = "AMBIGUOUS"
UNSCORABLE = "UNSCORABLE"

SCORABLE_LABELS = {ORDER_ERROR, NORMAL_PRESERVE, STRUCTURAL_BOUNDARY}
EXCLUDED_LABELS = {AMBIGUOUS, UNSCORABLE}


def _candidate_key(document: dict[str, Any], candidate: dict[str, Any]) -> tuple[Any, ...]:
    return (
        document["document_id"],
        candidate["page_no"],
        tuple(candidate["observed_order"]),
        tuple(candidate["proposed_order"]),
        candidate.get("type"),
        candidate.get("candidate_id"),
    )


def _label_key(label: dict[str, Any]) -> tuple[Any, ...]:
    return (
        label["document_id"],
        label["page_no"],
        tuple(label["observed_order"]),
    )


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def evaluate_labeled_candidates(
    labels_artifact: dict[str, Any], detector_artifact: dict[str, Any]
) -> dict[str, Any]:
    """Evaluate a detector audit against confirmed document-level gold labels.

    Candidate identity deliberately includes the document, page, observed order,
    and proposed order.  Candidate ids are local to each document and therefore
    are not globally unique.
    """

    if labels_artifact.get("schema_version") != "reading-order-gold-labels.v1":
        raise ValueError("unsupported labels schema")

    documents = {item["document_id"]: item for item in labels_artifact["documents"]}
    if len(documents) != len(labels_artifact["documents"]):
        raise ValueError("duplicate document_id")
    for document in documents.values():
        if document["split"] not in {"DEV", "HOLDOUT"}:
            raise ValueError(f"invalid split: {document['split']}")
        if document.get("annotation_status") not in {"PENDING", "CONFIRMED"}:
            raise ValueError("annotation_status must be PENDING or CONFIRMED")
        if document.get("coverage") not in {"CANDIDATES_ONLY", "FULL_PAGE"}:
            raise ValueError("coverage must be CANDIDATES_ONLY or FULL_PAGE")

    confirmed = [
        item for item in labels_artifact["labels"]
        if item.get("review_status") == CONFIRMED
    ]
    excluded = [item for item in confirmed if item["label"] in EXCLUDED_LABELS]
    scored = [item for item in confirmed if item["label"] in SCORABLE_LABELS]
    unknown = [item for item in confirmed if item["label"] not in SCORABLE_LABELS | EXCLUDED_LABELS]
    if unknown:
        raise ValueError(f"unsupported label: {unknown[0]['label']}")

    candidate_index: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    observed_index: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for detector_document in detector_artifact.get("documents", []):
        document_id = detector_document.get("document_id")
        if document_id is None:
            source_json = detector_document.get("source_json")
            matches = [
                key for key, value in documents.items()
                if value.get("source_json") == source_json
            ]
            if len(matches) == 1:
                document_id = matches[0]
        if document_id not in documents:
            continue
        for candidate in detector_document.get("candidates", []):
            candidate_index[_candidate_key({"document_id": document_id}, candidate)].append(candidate)
            observed_index[(document_id, candidate["page_no"], tuple(candidate["observed_order"]))].append(candidate)

    by_split: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for label in scored:
        if label["document_id"] not in documents:
            raise ValueError(f"unknown document_id: {label['document_id']}")
        by_split[documents[label["document_id"]]["split"]].append(label)

    def summarize(split: str, split_labels: list[dict[str, Any]]) -> dict[str, Any]:
        split_document_ids = {
            document_id for document_id, document in documents.items()
            if document["split"] == split
        }
        labeled_keys = {_label_key(item) for item in split_labels}
        unlabeled_auto_candidates = sum(
            candidate.get("decision") == "AUTO_REORDER_ELIGIBLE"
            and (key[0], key[1], key[2]) not in labeled_keys
            for key, candidates in candidate_index.items()
            if key[0] in split_document_ids
            for candidate in candidates
        )
        error_labels = [item for item in split_labels if item["label"] == ORDER_ERROR]
        normal_labels = [item for item in split_labels if item["label"] == NORMAL_PRESERVE]
        boundary_labels = [item for item in split_labels if item["label"] == STRUCTURAL_BOUNDARY]

        def candidates_for(item: dict[str, Any]) -> list[dict[str, Any]]:
            return observed_index.get(_label_key(item), [])

        def exact_candidates_for(item: dict[str, Any]) -> list[dict[str, Any]]:
            expected = item["expected_order"]
            return [candidate for candidate in candidates_for(item) if candidate["proposed_order"] == expected]

        detected_errors = [item for item in error_labels if candidates_for(item)]
        exact_errors = [item for item in error_labels if exact_candidates_for(item)]
        auto_true = [
            candidate
            for item in error_labels
            for candidate in candidates_for(item)
            if candidate.get("decision") == "AUTO_REORDER_ELIGIBLE"
            and candidate["proposed_order"] == item["expected_order"]
        ]
        unsafe_auto = [
            candidate
            for item in normal_labels + boundary_labels
            for candidate in candidates_for(item)
            if candidate.get("decision") == "AUTO_REORDER_ELIGIBLE"
        ]
        wrong_auto = [
            candidate
            for item in error_labels
            for candidate in candidates_for(item)
            if candidate.get("decision") == "AUTO_REORDER_ELIGIBLE"
            and candidate["proposed_order"] != item["expected_order"]
        ]
        auto_predictions = len(auto_true) + len(unsafe_auto) + len(wrong_auto)
        preserved_normal = len(normal_labels) - sum(
            any(
                candidate.get("decision") == "AUTO_REORDER_ELIGIBLE"
                for candidate in candidates_for(item)
            )
            for item in normal_labels
        )

        return {
            "confirmed_scorable_labels": len(split_labels),
            "order_errors": len(error_labels),
            "normal_preserve": len(normal_labels),
            "structural_boundaries": len(boundary_labels),
            "detected_order_errors": len(detected_errors),
            "exactly_corrected_order_errors": len(exact_errors),
            "auto_true_positive": len(auto_true),
            "auto_false_positive": len(unsafe_auto) + len(wrong_auto),
            "error_detection_recall": _safe_ratio(len(detected_errors), len(error_labels)),
            "exact_correction_recall": _safe_ratio(len(exact_errors), len(error_labels)),
            "auto_precision": (
                _safe_ratio(len(auto_true), auto_predictions)
                if unlabeled_auto_candidates == 0 else None
            ),
            "auto_coverage": _safe_ratio(len(auto_true), len(error_labels)),
            "normal_preservation_rate": _safe_ratio(preserved_normal, len(normal_labels)),
            "structural_boundary_violation_count": sum(
                candidate.get("decision") == "AUTO_REORDER_ELIGIBLE"
                for item in boundary_labels
                for candidate in candidates_for(item)
            ),
            "unlabeled_auto_candidate_count": unlabeled_auto_candidates,
            "precision_ready": unlabeled_auto_candidates == 0 and auto_predictions > 0,
        }

    split_metrics = {}
    for split in ("DEV", "HOLDOUT"):
        metrics = summarize(split, by_split.get(split, []))
        split_documents = [item for item in documents.values() if item["split"] == split]
        metrics["document_count"] = len(split_documents)
        metrics["full_page_confirmed_document_count"] = sum(
            item["annotation_status"] == "CONFIRMED" and item["coverage"] == "FULL_PAGE"
            for item in split_documents
        )
        metrics["recall_ready"] = bool(split_documents) and all(
            item["annotation_status"] == "CONFIRMED" and item["coverage"] == "FULL_PAGE"
            for item in split_documents
        )
        if not metrics["recall_ready"]:
            metrics["error_detection_recall"] = None
            metrics["exact_correction_recall"] = None
            metrics["auto_coverage"] = None
        split_metrics[split] = metrics
    label_counts = Counter(item["label"] for item in confirmed)
    return {
        "schema_version": "reading-order-metrics.v1",
        "heading_scope": "READ_ONLY_NOT_MODIFIED",
        "confirmed_label_counts": dict(label_counts),
        "excluded_confirmed_labels": len(excluded),
        "pending_label_count": sum(
            item.get("review_status") != CONFIRMED for item in labels_artifact["labels"]
        ),
        "detector_runtime": detector_artifact.get("runtime"),
        "splits": split_metrics,
        "holdout_ready": (
            split_metrics["HOLDOUT"]["recall_ready"]
            and split_metrics["HOLDOUT"]["precision_ready"]
            and split_metrics["HOLDOUT"]["normal_preserve"] > 0
        ),
    }
