from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from reasoner_runtime.config.loader import load_provider_profiles
from reasoner_runtime.config.models import ProviderProfile
from reasoner_runtime.core.models import ReasonerRequest, StructuredGenerationResult
from reasoner_runtime.providers import build_client, select_provider


ClientFactory = Callable[[ProviderProfile, int], Any]


def generate_structured(
    request: ReasonerRequest,
    *,
    provider_profiles: list[ProviderProfile] | None = None,
    provider_config_path: Path | None = None,
    client_factory: ClientFactory = build_client,
) -> StructuredGenerationResult:
    """Generate structured output through the configured provider boundary.

    Phase 0 keeps the model call as a placeholder, but the runtime seam is
    established here: callers may inject provider profiles directly or load
    them from a config path. Without either, the configured request target is
    converted into a single placeholder profile to preserve existing callers.
    """
    normalized_request = _normalize_request(request)
    profiles = _resolve_provider_profiles(
        normalized_request,
        provider_profiles=provider_profiles,
        provider_config_path=provider_config_path,
    )
    selected_profile = select_provider(
        normalized_request.configured_provider,
        normalized_request.configured_model,
        profiles,
    )
    _client = client_factory(selected_profile, normalized_request.max_retries)

    # scrub: #19 will replace this pass-through with scrub_input().
    _sanitized_messages = normalized_request.messages

    actual_provider = selected_profile.provider
    actual_model = selected_profile.model

    # call: #16 will replace this placeholder with the LiteLLM/Instructor call.
    _raw_output = ""

    # parse: #16 will parse raw model output into the requested target schema.
    parsed_result: dict[str, object] = {}

    # bundle: #17 will build the replay bundle from sanitized input and output.
    _replay_bundle = None

    return StructuredGenerationResult(
        parsed_result=parsed_result,
        actual_provider=actual_provider,
        actual_model=actual_model,
        token_usage={"prompt": 0, "completion": 0, "total": 0},
        cost_estimate=0.0,
        latency_ms=0,
    )


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
