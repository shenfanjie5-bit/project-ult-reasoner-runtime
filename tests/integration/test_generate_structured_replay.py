from __future__ import annotations

import json
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


def _request(**overrides: Any) -> ReasonerRequest:
    payload = {
        "request_id": "req-replay",
        "caller_module": "integration-test",
        "target_schema": "ReplayPayload",
        "messages": [{"role": "user", "content": "return a replay payload"}],
        "configured_provider": "openai",
        "configured_model": "gpt-4",
        "max_retries": 2,
    }
    payload.update(overrides)
    return ReasonerRequest(**payload)


def test_generate_structured_with_replay_returns_result_and_bundle() -> None:
    profile = ProviderProfile(provider="openai", model="gpt-4", fallback_priority=0)
    raw_output = ' \n{"score":7,"answer":"ok"}\n '
    call_result = StructuredCallResult(
        parsed_result={"answer": "ok", "score": 7},
        raw_output=raw_output,
        token_usage={"prompt": 3, "completion": 4, "total": 7},
        cost_estimate=0.02,
        latency_ms=11,
    )
    client = _FakeStructuredClient(call_result)
    client_factory_calls: list[tuple[ProviderProfile, int]] = []

    def client_factory(call_profile: ProviderProfile, max_retries: int) -> Any:
        client_factory_calls.append((call_profile, max_retries))
        return client

    result, bundle = generate_structured_with_replay(
        _request(),
        provider_profiles=[profile],
        schema_registry={"ReplayPayload": ReplayPayload},
        client_factory=client_factory,
    )

    assert isinstance(result, StructuredGenerationResult)
    assert isinstance(bundle, ReplayBundle)
    assert client_factory_calls == [(profile, 2)]
    assert client.calls[0]["response_model"] is ReplayPayload
    assert result.parsed_result == {"answer": "ok", "score": 7}
    assert result.actual_provider == "openai"
    assert result.actual_model == "gpt-4"
    assert result.fallback_path == ["openai/gpt-4"]
    assert result.retry_count == 0
    assert bundle.raw_output == raw_output
    assert bundle.parsed_result == result.parsed_result
    assert bundle.output_hash == sha256_text(raw_output)
    assert bundle.input_hash == sha256_text(bundle.sanitized_input)
    assert json.loads(bundle.sanitized_input) == _request().messages
    assert bundle.llm_lineage == {
        "provider": result.actual_provider,
        "model": result.actual_model,
        "fallback_path": result.fallback_path,
        "retry_count": result.retry_count,
    }


def test_replay_hashes_same_sanitized_messages_sent_to_client() -> None:
    profile = ProviderProfile(provider="openai", model="gpt-4", fallback_priority=0)
    raw_content = (
        "My name is Alice Smith, phone 415-555-1234, "
        "account: ACCT-998877."
    )
    request = _request(messages=[{"role": "user", "content": raw_content}])
    client = _FakeStructuredClient(
        StructuredCallResult(
            parsed_result={"answer": "ok", "score": 7},
            raw_output='{"answer":"ok","score":7}',
            token_usage={"prompt": 3, "completion": 4, "total": 7},
            cost_estimate=0.02,
            latency_ms=11,
        )
    )

    _result, bundle = generate_structured_with_replay(
        request,
        provider_profiles=[profile],
        schema_registry={"ReplayPayload": ReplayPayload},
        client_factory=lambda _profile, _max_retries: client,
    )

    sent_messages = client.calls[0]["messages"]
    serialized_sent_messages = json.dumps(
        sent_messages,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )

    assert bundle.sanitized_input == serialized_sent_messages
    assert bundle.input_hash == sha256_text(serialized_sent_messages)
    assert json.loads(bundle.sanitized_input) == sent_messages
    assert sent_messages != request.messages
    assert "Alice Smith" not in bundle.sanitized_input
    assert "415-555-1234" not in bundle.sanitized_input
    assert "ACCT-998877" not in bundle.sanitized_input
    assert "[REDACTED_NAME]" in bundle.sanitized_input
    assert "[REDACTED_PHONE]" in bundle.sanitized_input
    assert "[REDACTED_ACCOUNT]" in bundle.sanitized_input


def test_replay_redacts_spaced_account_digits_before_provider_and_hash() -> None:
    profile = ProviderProfile(provider="openai", model="gpt-4", fallback_priority=0)
    raw_content = (
        "card: 4111 1111 1111 1111; "
        "account number: 1234 5678 9012 3456."
    )
    request = _request(messages=[{"role": "user", "content": raw_content}])
    client = _FakeStructuredClient(
        StructuredCallResult(
            parsed_result={"answer": "ok", "score": 7},
            raw_output='{"answer":"ok","score":7}',
            token_usage={"prompt": 3, "completion": 4, "total": 7},
            cost_estimate=0.02,
            latency_ms=11,
        )
    )

    _result, bundle = generate_structured_with_replay(
        request,
        provider_profiles=[profile],
        schema_registry={"ReplayPayload": ReplayPayload},
        client_factory=lambda _profile, _max_retries: client,
    )

    sent_messages = client.calls[0]["messages"]
    serialized_sent_messages = json.dumps(
        sent_messages,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )

    assert sent_messages == [
        {
            "role": "user",
            "content": (
                "card: [REDACTED_ACCOUNT]; "
                "account number: [REDACTED_ACCOUNT]."
            ),
        }
    ]
    assert bundle.sanitized_input == serialized_sent_messages
    assert bundle.input_hash == sha256_text(serialized_sent_messages)
    assert json.loads(bundle.sanitized_input) == sent_messages
    for raw_fragment in ("4111", "1111", "1234", "5678", "9012", "3456"):
        assert raw_fragment not in bundle.sanitized_input


def test_generate_structured_keeps_structured_result_return_type() -> None:
    profile = ProviderProfile(provider="openai", model="gpt-4", fallback_priority=0)
    client = _FakeStructuredClient(
        StructuredCallResult(
            parsed_result={"answer": "ok", "score": 1},
            raw_output='{"answer":"ok","score":1}',
            token_usage={"prompt": 1, "completion": 1, "total": 2},
            cost_estimate=0.0,
            latency_ms=1,
        )
    )

    result = generate_structured(
        _request(),
        schema_registry={"ReplayPayload": ReplayPayload},
        provider_profiles=[profile],
        client_factory=lambda _profile, _max_retries: client,
    )

    assert isinstance(result, StructuredGenerationResult)


class _FakeStructuredClient:
    def __init__(self, result: StructuredCallResult) -> None:
        self.result = result
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
        return self.result
