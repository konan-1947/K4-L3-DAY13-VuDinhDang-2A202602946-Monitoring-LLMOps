from __future__ import annotations

from contextlib import contextmanager

import pytest

from app import agent as agent_module


class ManagedPrompt:
    version = 3

    def compile(self, **variables: str) -> str:
        return (
            f"Feature={variables['feature']}\n"
            f"Docs={variables['docs']}\n"
            f"Question={variables['message']}"
        )


class RecordingObservation:
    def __init__(self, kwargs: dict) -> None:
        self.kwargs = kwargs
        self.updates: list[dict] = []

    def update(self, **kwargs) -> None:
        self.updates.append(kwargs)


class RecordingChildClient:
    """Client giả hỗ trợ đầy đủ child observation API của Langfuse SDK v4."""

    def __init__(self) -> None:
        self.prompt = ManagedPrompt()
        self.children: list[RecordingObservation] = []
        self.span_updates: list[dict] = []

    def get_prompt(self, name: str, **kwargs):
        return self.prompt

    def update_current_span(self, **kwargs) -> None:
        self.span_updates.append(kwargs)

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        observation = RecordingObservation(kwargs)
        self.children.append(observation)
        yield observation


def _patch_agent(monkeypatch, client) -> None:
    monkeypatch.setenv("LANGFUSE_PROMPT_NAME", "day13-chat")
    monkeypatch.setenv("LANGFUSE_PROMPT_LABEL", "production")
    monkeypatch.setattr(agent_module, "get_langfuse_client", lambda: client)
    monkeypatch.setattr(agent_module, "tracing_enabled", lambda: True)

    @contextmanager
    def record_attributes(**kwargs):
        yield

    monkeypatch.setattr(agent_module, "propagate_attributes", record_attributes)


def _run_agent(monkeypatch, client, message: str = "Explain how monitoring metrics and traces work together"):
    _patch_agent(monkeypatch, client)
    agent = agent_module.LabAgent()
    result = agent_module.LabAgent.run.__wrapped__(
        agent,
        user_id="student-01",
        feature="qa",
        session_id="session-01",
        message=message,
        correlation_id="req-12345678",
    )
    return agent, result


def test_agent_opens_retrieval_and_generation_children(monkeypatch) -> None:
    client = RecordingChildClient()
    _run_agent(monkeypatch, client)

    assert [child.kwargs["name"] for child in client.children] == [
        "retrieval",
        "llm-generation",
    ]
    retrieval, generation = client.children

    assert retrieval.kwargs["as_type"] == "retriever"
    assert retrieval.kwargs["input"] == "Explain how monitoring metrics and traces work together"
    assert retrieval.updates[-1]["metadata"]["doc_count"] == 1
    assert "metrics detect incidents" in retrieval.updates[-1]["output"][0].lower()

    assert generation.kwargs["as_type"] == "generation"
    assert generation.kwargs["model"] == "claude-sonnet-4-5"
    assert generation.kwargs["prompt"] is client.prompt
    assert generation.kwargs["metadata"]["prompt_version"] == "3"
    assert generation.kwargs["metadata"]["prompt_label"] == "production"

    update = generation.updates[-1]
    assert update["model"] == "claude-sonnet-4-5"
    assert update["usage_details"]["input"] > 0
    assert update["usage_details"]["output"] > 0
    assert update["usage_details"]["total"] == (
        update["usage_details"]["input"] + update["usage_details"]["output"]
    )
    assert update["cost_details"]["input"] > 0
    assert update["cost_details"]["output"] > 0
    assert update["metadata"]["ttft_ms"] > 0
    assert "Starter answer" in update["output"]


def test_generation_cost_details_match_reported_cost(monkeypatch) -> None:
    client = RecordingChildClient()
    _agent, result = _run_agent(monkeypatch, client)

    cost_details = client.children[1].updates[-1]["cost_details"]
    usage = client.children[1].updates[-1]["usage_details"]

    assert usage["input"] == result.tokens_in
    assert usage["output"] == result.tokens_out
    assert round(cost_details["input"] + cost_details["output"], 6) == result.cost_usd


def test_child_observations_do_not_capture_raw_pii(monkeypatch) -> None:
    client = RecordingChildClient()
    _run_agent(
        monkeypatch,
        client,
        "Email me at student@vinuni.edu.vn, call 0912345678, card 4111 1111 1111 1111",
    )

    captured = repr(
        [(child.kwargs, child.updates) for child in client.children]
    )
    assert "student@vinuni.edu.vn" not in captured
    assert "0912345678" not in captured
    assert "4111 1111 1111 1111" not in captured
    assert "[REDACTED_EMAIL]" in captured
    assert "[REDACTED_PHONE_VN]" in captured
    assert "[REDACTED_CREDIT_CARD]" in captured


def test_retrieval_failure_marks_child_observation_as_error(monkeypatch) -> None:
    client = RecordingChildClient()
    _patch_agent(monkeypatch, client)

    def failing_retrieve(message: str) -> list[str]:
        raise RuntimeError("Vector store timeout")

    monkeypatch.setattr(agent_module, "retrieve", failing_retrieve)
    agent = agent_module.LabAgent()

    with pytest.raises(RuntimeError):
        agent_module.LabAgent.run.__wrapped__(
            agent,
            user_id="student-01",
            feature="qa",
            session_id="session-01",
            message="Explain traces",
            correlation_id="req-12345678",
        )

    assert len(client.children) == 1
    assert client.children[0].kwargs["as_type"] == "retriever"
    assert client.children[0].updates[-1] == {
        "level": "ERROR",
        "status_message": "RuntimeError",
    }


def test_agent_runs_without_child_observation_support(monkeypatch) -> None:
    class MinimalClient:
        def __init__(self) -> None:
            self.prompt = ManagedPrompt()

        def get_prompt(self, name: str, **kwargs):
            return self.prompt

        def update_current_span(self, **kwargs) -> None:
            return None

    client = MinimalClient()
    _agent, result = _run_agent(monkeypatch, client)

    assert result.answer.startswith("Starter answer")
    assert result.cost_usd > 0
