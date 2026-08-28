from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import asdict
from typing import Iterator

from .models import LabCase, MetricScore


class PhoenixTelemetry:
    def __init__(self) -> None:
        try:
            from phoenix.otel import register
        except ImportError as exc:
            raise RuntimeError("먼저 전용 requirements.txt를 설치하세요.") from exc

        endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006/v1/traces")
        project = os.getenv("PHOENIX_PROJECT_NAME", "agent-eval-learning-lab")
        self.provider = register(
            endpoint=endpoint,
            protocol="http/protobuf",
            project_name=project,
            batch=False,
        )
        self.tracer = self.provider.get_tracer("otel-eval-lab")
        self._annotation_client = None
        self._pending_annotations: list[tuple[str, MetricScore]] = []

    @contextmanager
    def case_span(self, case: LabCase) -> Iterator[object]:
        with self.tracer.start_as_current_span(f"evaluation.case.{case.case_id}") as span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("eval.lab.protocol", "OTEL_EVAL_LAB_V2")
            span.set_attribute("eval.lab.official_score_eligible", False)
            span.set_attribute("eval.lab.case_id", case.case_id)
            span.set_attribute("eval.lab.source", case.source)
            span.set_attribute("input.value", case.input)
            span.set_attribute("output.value", case.actual_output)
            span.set_attribute("eval.lab.retrieval_context_count", len(case.retrieval_context))
            span.set_attribute("eval.lab.retrieved_context_ids", case.retrieved_context_ids)
            span.set_attribute("eval.lab.reference_context_ids", case.reference_context_ids)
            span.set_attribute("eval.lab.tools_called", case.tools_called)
            span.set_attribute("eval.lab.metadata", json.dumps(case.metadata, ensure_ascii=False, default=str))
            yield span

    def add_score(self, span: object, score: MetricScore) -> None:
        span.set_attribute(f"eval.{score.evaluator}.{score.metric}.score", score.score)
        if score.passed is not None:
            span.set_attribute(f"eval.{score.evaluator}.{score.metric}.passed", score.passed)
        if score.reason:
            span.set_attribute(f"eval.{score.evaluator}.{score.metric}.reason", score.reason)

        from opentelemetry.trace import format_span_id

        span_id = format_span_id(span.get_span_context().span_id)
        self._pending_annotations.append((span_id, score))

    def flush(self) -> None:
        self.provider.force_flush()
        if not self._pending_annotations:
            return
        try:
            from phoenix.client import Client

            if self._annotation_client is None:
                self._annotation_client = Client(
                    base_url=os.getenv("PHOENIX_BASE_URL", "http://localhost:6006")
                )
            for span_id, score in self._pending_annotations:
                self._annotation_client.spans.add_span_annotation(
                    annotation_name=f"{score.evaluator}.{score.metric}",
                    annotator_kind="LLM" if score.evaluator == "ragas" else "CODE",
                    span_id=span_id,
                    label=(
                        ("PASS" if score.passed else "FAIL")
                        if score.passed is not None
                        else None
                    ),
                    score=score.score,
                    explanation=score.reason,
                    metadata={"protocol": "OTEL_EVAL_LAB_V2", "evaluator": score.evaluator},
                )
            self._pending_annotations.clear()
        except Exception as exc:
            raise RuntimeError(f"Phoenix annotation 기록 실패: {exc}") from exc


def score_as_json(score: MetricScore) -> dict[str, object]:
    return asdict(score)
