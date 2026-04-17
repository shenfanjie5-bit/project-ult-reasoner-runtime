from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from reasoner_runtime.config import ProviderProfile
from reasoner_runtime.core import (
    ReasonerRequest,
    StructuredGenerationResult,
    generate_structured,
    generate_structured_with_replay,
)
from reasoner_runtime.replay import ReplayBundle, sha256_text
from reasoner_runtime.structured import StructuredCallResult


class ReplayPayload(BaseModel):
    answer: str
    score: int


class _FakeStructuredClient:
    def __init__(self, call_result: StructuredCallResult) -> None:
        self.call_result = call_result
        self.calls: list[dict[str, Any]] = []

    def create_structured(
        self,
        *,
        messages: list[dict[str, Any]],
        response_model: type[BaseModel],
    ) -> StructuredCallResult:
        self.calls.append(
            {
                "messages": messages,
                "response_model": response_model,
            }
        )
        return self.call_result


def _request() -> ReasonerRequest:
    return ReasonerRequest(
        request_id="req-replay",
        caller_module="integration-test",
        target_schema="ReplayPayload",
        messages=[{"role": "user", "content": "hello"}],
        configured_provider="openai",
        configured_model="gpt-4",
        max_retries=2,
    )


def test_generate_structured_with_replay_returns_result_and_bundle() -> None:
    request = _request()
    raw_output = ' \n{"answer":"ok","score":7}\n '
    call_result = StructuredCallResult(
        parsed_result={"answer": "ok", "score": 7},
        raw_output=raw_output,
        token_usage={"prompt": 3, "completion": 4, "total": 7},
        cost_estimate=0.05,
        latency_ms=12,
    )
    client = _FakeStructuredClient(call_result)
    profile = ProviderProfile(provider="openai", model="gpt-4", fallback_priority=0)

    def client_factory(provider_profile: ProviderProfile, max_retries: int) -> Any:
        assert provider_profile == profile
        assert max_retries == request.max_retries
        return client

    result, bundle = generate_structured_with_replay(
        request,
        schema_registry={"ReplayPayload": ReplayPayload},
        provider_profiles=[profile],
        client_factory=client_factory,
    )

    assert isinstance(result, StructuredGenerationResult)
    assert isinstance(bundle, ReplayBundle)
    assert client.calls[0]["messages"] is request.messages
    assert client.calls[0]["response_model"] is ReplayPayload
    assert result.parsed_result == {"answer": "ok", "score": 7}
    assert result.actual_provider == "openai"
    assert result.actual_model == "gpt-4"
    assert result.fallback_path == ["openai/gpt-4"]
    assert result.retry_count == 0
    assert bundle.sanitized_input == '[{"content":"hello","role":"user"}]'
    assert bundle.input_hash == sha256_text(bundle.sanitized_input)
    assert bundle.raw_output == raw_output
    assert bundle.output_hash == sha256_text(raw_output)
    assert bundle.parsed_result == result.parsed_result
    assert bundle.llm_lineage["provider"] == result.actual_provider
    assert bundle.llm_lineage["model"] == result.actual_model
    assert bundle.llm_lineage["fallback_path"] == result.fallback_path
    assert bundle.llm_lineage["retry_count"] == result.retry_count


def test_generate_structured_with_replay_accepts_issue_signature_order() -> None:
    call_result = StructuredCallResult(
        parsed_result={"answer": "ok", "score": 7},
        raw_output='{"answer":"ok","score":7}',
        token_usage={"prompt": 1, "completion": 1, "total": 2},
        cost_estimate=0.0,
        latency_ms=1,
    )
    client = _FakeStructuredClient(call_result)
    profile = ProviderProfile(provider="openai", model="gpt-4", fallback_priority=0)

    def client_factory(provider_profile: ProviderProfile, max_retries: int) -> Any:
        return client

    result, bundle = generate_structured_with_replay(
        _request(),
        [profile],
        {"ReplayPayload": ReplayPayload},
        client_factory=client_factory,
    )

    assert result.parsed_result == {"answer": "ok", "score": 7}
    assert bundle.parsed_result == result.parsed_result


def test_generate_structured_keeps_structured_generation_result_return_type() -> None:
    call_result = StructuredCallResult(
        parsed_result={"answer": "ok", "score": 7},
        raw_output='{"answer":"ok","score":7}',
        token_usage={"prompt": 1, "completion": 1, "total": 2},
        cost_estimate=0.0,
        latency_ms=1,
    )
    client = _FakeStructuredClient(call_result)

    def client_factory(provider_profile: ProviderProfile, max_retries: int) -> Any:
        return client

    result = generate_structured(
        _request(),
        schema_registry={"ReplayPayload": ReplayPayload},
        client_factory=client_factory,
    )

    assert isinstance(result, StructuredGenerationResult)
    assert not isinstance(result, tuple)
