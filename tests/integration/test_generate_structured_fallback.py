from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel

from reasoner_runtime.config import ProviderProfile
from reasoner_runtime.core import ReasonerRequest, generate_structured


class FallbackPayload(BaseModel):
    answer: str
    confidence: float


def _request(**overrides: Any) -> ReasonerRequest:
    payload = {
        "request_id": "req-integration-fallback",
        "caller_module": "integration-test",
        "target_schema": "FallbackPayload",
        "messages": [{"role": "user", "content": "return a structured answer"}],
        "configured_provider": "openai",
        "configured_model": "gpt-4",
        "max_retries": 2,
    }
    payload.update(overrides)
    return ReasonerRequest(**payload)


def test_generate_structured_falls_back_after_provider_infra_failure() -> None:
    primary = ProviderProfile(provider="openai", model="gpt-4", fallback_priority=5)
    fallback = ProviderProfile(
        provider="anthropic",
        model="claude-sonnet-4.5",
        fallback_priority=0,
    )
    client_factory_calls: list[tuple[ProviderProfile, int]] = []
    completion_calls: list[str] = []

    def client_factory(profile: ProviderProfile, max_retries: int) -> Any:
        client_factory_calls.append((profile, max_retries))
        return SimpleNamespace(
            chat=SimpleNamespace(
                completions=_FallbackCompletions(profile, completion_calls),
            )
        )

    result = generate_structured(
        _request(),
        schema_registry={"FallbackPayload": FallbackPayload},
        provider_profiles=[fallback, primary],
        client_factory=client_factory,
    )

    assert client_factory_calls == [(primary, 2), (fallback, 2)]
    assert completion_calls == ["openai/gpt-4", "anthropic/claude-sonnet-4.5"]
    assert result.parsed_result == {"answer": "fallback-ok", "confidence": 0.75}
    assert result.actual_provider == "anthropic"
    assert result.actual_model == "claude-sonnet-4.5"
    assert result.fallback_path == completion_calls
    assert result.retry_count == 0


def test_generate_structured_retries_parse_failure_on_current_provider() -> None:
    primary = ProviderProfile(provider="openai", model="gpt-4", fallback_priority=0)
    fallback = ProviderProfile(
        provider="anthropic",
        model="claude-sonnet-4.5",
        fallback_priority=1,
    )
    client_factory_calls: list[tuple[ProviderProfile, int]] = []
    completion_responses: list[Any] = [
        {"answer": "missing confidence"},
        (
            FallbackPayload(answer="retry-ok", confidence=0.9),
            SimpleNamespace(
                choices=[
                    {"message": {"content": '{"answer":"retry-ok","confidence":0.9}'}}
                ],
                token_usage={"prompt": 3, "completion": 4, "total": 7},
                cost_estimate=0.01,
                latency_ms=11,
            ),
        ),
    ]

    def client_factory(profile: ProviderProfile, max_retries: int) -> Any:
        client_factory_calls.append((profile, max_retries))
        return SimpleNamespace(
            chat=SimpleNamespace(
                completions=_RetryCompletions(completion_responses),
            )
        )

    result = generate_structured(
        _request(max_retries=2),
        schema_registry={"FallbackPayload": FallbackPayload},
        provider_profiles=[primary, fallback],
        client_factory=client_factory,
    )

    assert client_factory_calls == [(primary, 2), (primary, 2)]
    assert result.parsed_result == {"answer": "retry-ok", "confidence": 0.9}
    assert result.actual_provider == "openai"
    assert result.actual_model == "gpt-4"
    assert result.fallback_path == ["openai/gpt-4"]
    assert result.retry_count == 1
    assert result.token_usage == {"prompt": 3, "completion": 4, "total": 7}


def test_generate_structured_normalizes_provider_qualified_fallback_path() -> None:
    profile = ProviderProfile(
        provider="openai",
        model="openai/gpt-4",
        fallback_priority=0,
    )

    def client_factory(profile: ProviderProfile, max_retries: int) -> Any:
        return SimpleNamespace(
            chat=SimpleNamespace(
                completions=_StaticCompletions(
                    FallbackPayload(answer="ok", confidence=1.0),
                ),
            )
        )

    result = generate_structured(
        _request(configured_model="openai/gpt-4"),
        schema_registry={"FallbackPayload": FallbackPayload},
        provider_profiles=[profile],
        client_factory=client_factory,
    )

    assert result.fallback_path == ["openai/gpt-4"]
    assert result.actual_model == "openai/gpt-4"


class _FallbackCompletions:
    def __init__(
        self,
        profile: ProviderProfile,
        completion_calls: list[str],
    ) -> None:
        self.profile = profile
        self.completion_calls = completion_calls

    def create_with_completion(self, **kwargs: Any) -> Any:
        target = f"{self.profile.provider}/{self.profile.model}"
        self.completion_calls.append(target)
        if self.profile.provider == "openai":
            raise ConnectionError("primary unavailable")

        return (
            FallbackPayload(answer="fallback-ok", confidence=0.75),
            SimpleNamespace(
                choices=[
                    {
                        "message": {
                            "content": '{"answer":"fallback-ok","confidence":0.75}'
                        }
                    }
                ],
                token_usage={"prompt": 9, "completion": 4, "total": 13},
                cost_estimate=0.02,
                latency_ms=41,
            ),
        )


class _RetryCompletions:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses

    def create_with_completion(self, **kwargs: Any) -> Any:
        return self.responses.pop(0)


class _StaticCompletions:
    def __init__(self, payload: FallbackPayload) -> None:
        self.payload = payload

    def create_with_completion(self, **kwargs: Any) -> Any:
        return self.payload
