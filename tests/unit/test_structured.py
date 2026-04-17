from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from reasoner_runtime.config import ProviderProfile
from reasoner_runtime.core import ReasonerRequest, StructuredGenerationResult
from reasoner_runtime.providers import ParseValidationError, build_client
from reasoner_runtime.providers import client as provider_client
from reasoner_runtime.structured import (
    StructuredCallResult,
    resolve_response_model,
    run_structured_call,
)


class AnswerPayload(BaseModel):
    answer: str
    score: int


def _request(messages: list[dict[str, Any]] | None = None) -> ReasonerRequest:
    return ReasonerRequest(
        request_id="req-1",
        caller_module="unit-test",
        target_schema="AnswerPayload",
        messages=messages or [{"role": "user", "content": "answer directly"}],
        configured_provider="openai",
        configured_model="gpt-4",
        max_retries=2,
    )


def test_resolve_response_model_returns_registered_pydantic_model() -> None:
    assert (
        resolve_response_model("AnswerPayload", {"AnswerPayload": AnswerPayload})
        is AnswerPayload
    )


def test_resolve_response_model_rejects_missing_schema() -> None:
    with pytest.raises(ParseValidationError, match="not registered"):
        resolve_response_model("MissingPayload", {})


def test_resolve_response_model_rejects_non_pydantic_schema() -> None:
    with pytest.raises(ParseValidationError, match="Pydantic BaseModel"):
        resolve_response_model("BadPayload", {"BadPayload": dict})  # type: ignore[dict-item]


def test_run_structured_call_preserves_messages_and_runtime_fields() -> None:
    messages = [{"role": "user", "content": "keep this exact message"}]
    completion = SimpleNamespace(
        choices=[{"message": {"content": '{"answer":"ok","score":7}'}}],
        usage={"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
        response_cost=0.003,
        latency_ms=23,
    )
    completions = _FakeCompletions((AnswerPayload(answer="ok", score=7), completion))
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    request = _request(messages)

    result = run_structured_call(client, request, AnswerPayload)

    assert completions.calls[0]["messages"] is request.messages
    assert completions.calls[0]["response_model"] is AnswerPayload
    assert result.parsed_result == {"answer": "ok", "score": 7}
    assert result.raw_output == '{"answer":"ok","score":7}'
    assert result.token_usage == {"prompt": 11, "completion": 5, "total": 16}
    assert result.cost_estimate == 0.003
    assert result.latency_ms == 23


def test_run_structured_call_validates_dict_payload_into_response_model() -> None:
    completions = _FakeCompletions({"answer": "from-dict", "score": 3})
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    result = run_structured_call(client, _request(), AnswerPayload)

    assert result.parsed_result == {"answer": "from-dict", "score": 3}
    assert result.raw_output == '{"answer":"from-dict","score":3}'
    assert result.token_usage == {"prompt": 0, "completion": 0, "total": 0}
    assert result.cost_estimate == 0.0


def test_run_structured_call_raises_typed_parse_error_for_invalid_payload() -> None:
    completions = _FakeCompletions({"answer": "missing score"})
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    with pytest.raises(ParseValidationError):
        run_structured_call(client, _request(), AnswerPayload)


def test_build_client_signature_requires_explicit_max_retries() -> None:
    signature = inspect.signature(build_client)

    assert signature.parameters["max_retries"].default is inspect.Parameter.empty


def test_build_client_passes_profile_and_max_retries_to_instructor_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completions = _FakeCompletions(AnswerPayload(answer="ok", score=1))
    instructor_client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions),
    )
    monkeypatch.setattr(
        provider_client,
        "_create_instructor_client",
        lambda: instructor_client,
    )
    profile = ProviderProfile(
        provider="openai",
        model="gpt-4",
        timeout_ms=2500,
        fallback_priority=0,
    )
    messages = [{"role": "user", "content": "hello"}]

    client = build_client(profile, 4)
    client.create_structured(messages=messages, response_model=AnswerPayload)

    assert client.profile == profile
    assert client.max_retries == 4
    assert completions.calls[0]["model"] == "openai/gpt-4"
    assert completions.calls[0]["messages"] is messages
    assert completions.calls[0]["response_model"] is AnswerPayload
    assert completions.calls[0]["max_retries"] == 4
    assert completions.calls[0]["timeout"] == 2.5


def test_structured_result_models_reject_negative_runtime_values() -> None:
    with pytest.raises(ValidationError):
        StructuredCallResult(
            parsed_result={},
            raw_output="{}",
            token_usage={"prompt": -1, "completion": 0, "total": 0},
            cost_estimate=0.0,
            latency_ms=0,
        )

    with pytest.raises(ValidationError):
        StructuredGenerationResult(
            parsed_result={},
            actual_provider="openai",
            actual_model="gpt-4",
            retry_count=-1,
            token_usage={"prompt": 0, "completion": 0, "total": 0},
            cost_estimate=0.0,
            latency_ms=0,
        )


def test_provider_profile_rejects_invalid_numeric_values() -> None:
    with pytest.raises(ValidationError):
        ProviderProfile(provider="openai", model="gpt-4", timeout_ms=0)

    with pytest.raises(ValidationError):
        ProviderProfile(provider="openai", model="gpt-4", rate_limit_rpm=0)


class _FakeCompletions:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def create_with_completion(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.response

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.response
