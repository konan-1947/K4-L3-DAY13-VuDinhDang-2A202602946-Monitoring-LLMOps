from __future__ import annotations

import os
import time
from dataclasses import dataclass

from . import metrics
from .mock_llm import FakeLLM, FakeResponse
from .mock_rag import retrieve
from .pii import hash_user_id, scrub_text, summarize_text
from .prompt_management import ResolvedPrompt, resolve_prompt
from .tracing import (
    child_observation,
    get_langfuse_client,
    observe,
    propagate_attributes,
    tracing_enabled,
)

COST_INPUT_PER_MILLION_USD = 3.0
COST_OUTPUT_PER_MILLION_USD = 15.0


@dataclass
class AgentResult:
    answer: str
    latency_ms: int
    ttft_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    quality_score: float


class LabAgent:
    def __init__(self, model: str = "claude-sonnet-4-5") -> None:
        self.model = model
        self.llm = FakeLLM(model=model)

    @observe(name="lab-agent-run", as_type="agent", capture_input=False, capture_output=False)
    def run(
        self,
        user_id: str,
        feature: str,
        session_id: str,
        message: str,
        correlation_id: str,
    ) -> AgentResult:
        langfuse_client = get_langfuse_client()
        with propagate_attributes(
            user_id=hash_user_id(user_id),
            session_id=session_id,
            tags=["lab", feature, self.model],
            trace_name="day13-agent-request",
            environment=os.getenv("APP_ENV", "dev"),
            metadata={
                "feature": feature,
                "model": self.model,
                "correlation_id": correlation_id,
            },
        ):
            started = time.perf_counter()
            docs = self._retrieve_observed(langfuse_client, message)
            prompt = resolve_prompt(
                langfuse_client,
                feature=feature,
                docs=docs,
                message=message,
                enabled=tracing_enabled(),
            )
            langfuse_client.update_current_span(
                metadata={
                    "doc_count": len(docs),
                    "query_preview": summarize_text(message),
                    "prompt_name": prompt.name,
                    "prompt_label": prompt.label,
                    "prompt_version": prompt.version,
                    "prompt_source": prompt.source,
                    "prompt_fetch_error": prompt.fetch_error or "",
                },
                version=prompt.version,
            )
            with propagate_attributes(prompt=prompt.managed_prompt):
                response = self._generate_observed(langfuse_client, prompt)
            quality_score = self._heuristic_quality(message, response.text, docs)
            latency_ms = int((time.perf_counter() - started) * 1000)
            cost_usd = self._estimate_cost(response.usage.input_tokens, response.usage.output_tokens)

        metrics.record_request(
            latency_ms=latency_ms,
            ttft_ms=response.ttft_ms,
            cost_usd=cost_usd,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            quality_score=quality_score,
        )

        return AgentResult(
            answer=response.text,
            latency_ms=latency_ms,
            ttft_ms=response.ttft_ms,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            cost_usd=cost_usd,
            quality_score=quality_score,
        )

    def _retrieve_observed(self, langfuse_client: object, message: str) -> list[str]:
        query_preview = summarize_text(message, 200)
        with child_observation(
            langfuse_client,
            name="retrieval",
            as_type="retriever",
            input=query_preview,
            metadata={"query_preview": query_preview},
        ) as observation:
            try:
                docs = retrieve(message)
            except Exception as exc:
                observation.update(level="ERROR", status_message=type(exc).__name__)
                raise
            safe_docs = [scrub_text(doc) for doc in docs]
            observation.update(
                output=safe_docs,
                metadata={"doc_count": len(safe_docs)},
            )
            return docs

    def _generate_observed(
        self, langfuse_client: object, prompt: ResolvedPrompt
    ) -> FakeResponse:
        with child_observation(
            langfuse_client,
            name="llm-generation",
            as_type="generation",
            model=self.model,
            input=scrub_text(prompt.text),
            prompt=prompt.managed_prompt,
            metadata={
                "prompt_name": prompt.name,
                "prompt_label": prompt.label,
                "prompt_version": prompt.version,
                "prompt_source": prompt.source,
            },
        ) as observation:
            response = self.llm.generate(prompt.text)
            observation.update(
                output=scrub_text(response.text),
                model=response.model,
                usage_details={
                    "input": response.usage.input_tokens,
                    "output": response.usage.output_tokens,
                    "total": response.usage.input_tokens + response.usage.output_tokens,
                },
                cost_details=self._cost_breakdown(
                    response.usage.input_tokens, response.usage.output_tokens
                ),
                metadata={"ttft_ms": response.ttft_ms},
            )
            return response

    def _cost_breakdown(self, tokens_in: int, tokens_out: int) -> dict[str, float]:
        return {
            "input": round((tokens_in / 1_000_000) * COST_INPUT_PER_MILLION_USD, 8),
            "output": round((tokens_out / 1_000_000) * COST_OUTPUT_PER_MILLION_USD, 8),
        }

    def _estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        breakdown = self._cost_breakdown(tokens_in, tokens_out)
        return round(breakdown["input"] + breakdown["output"], 6)

    def _heuristic_quality(self, question: str, answer: str, docs: list[str]) -> float:
        score = 0.5
        if docs:
            score += 0.2
        if len(answer) > 40:
            score += 0.1
        if question.lower().split()[0:1] and any(token in answer.lower() for token in question.lower().split()[:3]):
            score += 0.1
        if "[REDACTED" in answer:
            score -= 0.2
        return round(max(0.0, min(1.0, score)), 2)
