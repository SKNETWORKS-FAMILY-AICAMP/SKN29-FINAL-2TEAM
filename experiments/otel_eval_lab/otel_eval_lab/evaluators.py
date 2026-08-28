from __future__ import annotations

import asyncio
import os
import warnings

from .models import LabCase, MetricScore


def run_deepeval_answer_relevancy(case: LabCase) -> MetricScore:
    os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
    os.environ.setdefault("DEEPEVAL_RETRY_MAX_ATTEMPTS", "1")
    os.environ.setdefault("DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS", "60")
    try:
        from deepeval.metrics import AnswerRelevancyMetric
        from deepeval.models import GPTModel
        from deepeval.test_case import LLMTestCase
    except ImportError as exc:
        raise RuntimeError("DeepEval이 전용 환경에 설치되지 않았습니다.") from exc

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("DeepEval LLM 평가에는 OPENAI_API_KEY가 필요합니다.")
    judge_model = GPTModel(
        model=os.getenv("DEEPEVAL_JUDGE_MODEL", "gpt-4o-mini"),
        api_key=api_key,
        base_url=os.getenv("OPENAI_BASE_URL"),
        timeout=60.0,
    )
    test_case = LLMTestCase(
        input=case.input,
        actual_output=case.actual_output,
    )
    metric = AnswerRelevancyMetric(
        threshold=0.7,
        include_reason=True,
        async_mode=False,
        model=judge_model,
    )
    metric.measure(test_case)
    return MetricScore(
        evaluator="deepeval",
        metric="answer_relevancy",
        score=float(metric.score),
        passed=bool(metric.is_successful()),
        reason=str(metric.reason or ""),
    )


def run_ragas_id_context_metrics(case: LabCase) -> list[MetricScore]:
    if not case.reference_context_ids:
        raise ValueError(f"{case.case_id}: reference_context_ids가 필요합니다.")
    try:
        from ragas import SingleTurnSample
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from ragas.metrics import IDBasedContextPrecision, IDBasedContextRecall
    except ImportError as exc:
        raise RuntimeError("Ragas가 전용 환경에 설치되지 않았습니다.") from exc

    async def evaluate() -> list[MetricScore]:
        sample = SingleTurnSample(
            retrieved_context_ids=case.retrieved_context_ids,
            reference_context_ids=case.reference_context_ids,
        )
        precision = await IDBasedContextPrecision().single_turn_ascore(sample)
        recall = await IDBasedContextRecall().single_turn_ascore(sample)
        return [
            MetricScore(
                evaluator="ragas",
                metric="id_context_precision",
                score=float(precision),
                reason="검색 문서 ID 중 필수 문서 ID가 차지하는 비율",
            ),
            MetricScore(
                evaluator="ragas",
                metric="id_context_recall",
                score=float(recall),
                reason="필수 문서 ID 중 실제 검색된 문서 ID의 비율",
            ),
        ]

    return asyncio.run(evaluate())


def run_ragas_faithfulness(case: LabCase) -> MetricScore:
    if not case.retrieval_context:
        raise ValueError(f"{case.case_id}: retrieval_context가 필요합니다.")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Ragas LLM 평가에는 OPENAI_API_KEY가 필요합니다.")

    try:
        from openai import AsyncOpenAI
        from ragas.llms import llm_factory
        from ragas.metrics.collections import Faithfulness
    except ImportError as exc:
        raise RuntimeError("Ragas가 전용 환경에 설치되지 않았습니다.") from exc

    client_args: dict[str, str] = {"api_key": api_key}
    if os.getenv("OPENAI_BASE_URL"):
        client_args["base_url"] = os.environ["OPENAI_BASE_URL"]
    async def evaluate() -> MetricScore:
        async with AsyncOpenAI(**client_args) as client:
            llm = llm_factory(
                os.getenv("RAGAS_JUDGE_MODEL", "gpt-4o-mini"),
                client=client,
                max_tokens=int(os.getenv("RAGAS_MAX_TOKENS", "8192")),
            )
            metric = Faithfulness(llm=llm)
            result = await metric.ascore(
                user_input=case.input,
                response=case.actual_output,
                retrieved_contexts=case.retrieval_context,
            )
        value = float(result.value)
        return MetricScore(
            evaluator="ragas",
            metric="faithfulness",
            score=value,
            passed=value >= 0.7,
            reason=str(result.reason or ""),
        )

    return asyncio.run(evaluate())
