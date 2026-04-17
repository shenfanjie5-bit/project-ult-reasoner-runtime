from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from reasoner_runtime.config.loader import load_provider_profiles
from reasoner_runtime.config.models import ProviderProfile
from reasoner_runtime.core.models import ReasonerRequest, StructuredGenerationResult
from reasoner_runtime.providers import build_client, execute_with_fallback
from reasoner_runtime.structured import resolve_response_model, run_structured_call


ClientFactory = Callable[[ProviderProfile, int], Any]


def generate_structured(
    request: ReasonerRequest,
    *,
    schema_registry: Mapping[str, type[BaseModel]],
    provider_profiles: list[ProviderProfile] | None = None,
    provider_config_path: Path | None = None,
    client_factory: ClientFactory = build_client,
) -> StructuredGenerationResult:
    """Generate structured output through the configured provider boundary.

    Callers may inject provider profiles directly or load them from a config
    path. Without either, the configured request target is converted into a
    single profile to preserve the provider boundary.
    """
    normalized_request = _normalize_request(request)
    profiles = _resolve_provider_profiles(
        normalized_request,
        provider_profiles=provider_profiles,
        provider_config_path=provider_config_path,
    )

    # scrub: #19 will replace this pass-through with scrub_input().
    _sanitized_messages = normalized_request.messages

    response_model = resolve_response_model(
        normalized_request.target_schema,
        schema_registry,
    )

    def call_provider(
        call_request: ReasonerRequest,
        profile: ProviderProfile,
        _parse_retry_index: int,
    ) -> StructuredGenerationResult:
        client = client_factory(profile, call_request.max_retries)
        call_result = run_structured_call(client, call_request, response_model)
        _raw_output = call_result.raw_output

        # bundle: #17 will build the replay bundle from sanitized input and output.
        _replay_bundle = None

        return StructuredGenerationResult(
            parsed_result=call_result.parsed_result,
            actual_provider=profile.provider,
            actual_model=profile.model,
            fallback_path=[],
            token_usage=call_result.token_usage,
            cost_estimate=call_result.cost_estimate,
            latency_ms=call_result.latency_ms,
        )

    result, _decision = execute_with_fallback(
        normalized_request,
        profiles,
        call_provider,
    )
    return result


def _resolve_provider_profiles(
    request: ReasonerRequest,
    *,
    provider_profiles: list[ProviderProfile] | None,
    provider_config_path: Path | None,
) -> list[ProviderProfile]:
    if provider_profiles is not None and provider_config_path is not None:
        raise ValueError(
            "provider_profiles and provider_config_path cannot both be provided"
        )

    if provider_profiles is not None:
        return provider_profiles

    if provider_config_path is not None:
        return load_provider_profiles(provider_config_path)

    return [
        ProviderProfile(
            provider=request.configured_provider,
            model=request.configured_model,
            fallback_priority=0,
        )
    ]


def _normalize_request(request: ReasonerRequest) -> ReasonerRequest:
    if not isinstance(request, ReasonerRequest):
        raise TypeError("request must be a ReasonerRequest")

    if request.max_retries < 0:
        raise ValueError("max_retries must be greater than or equal to 0")

    required_text_fields = {
        "caller_module": request.caller_module,
        "target_schema": request.target_schema,
        "configured_provider": request.configured_provider,
        "configured_model": request.configured_model,
    }
    missing_fields = [
        field_name
        for field_name, value in required_text_fields.items()
        if not value.strip()
    ]
    if missing_fields:
        joined_fields = ", ".join(missing_fields)
        raise ValueError(f"required request fields cannot be empty: {joined_fields}")

    if request.request_id.strip():
        return request

    return request.model_copy(update={"request_id": str(uuid4())})

