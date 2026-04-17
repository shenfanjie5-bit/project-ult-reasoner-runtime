from __future__ import annotations

from collections.abc import Callable, Mapping
from json import JSONDecodeError
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ValidationError as PydanticValidationError

from reasoner_runtime.callbacks import (
    build_callback_backends,
    configure_litellm_callbacks,
)
from reasoner_runtime.config.loader import (
    load_callback_profile,
    load_provider_profiles,
)
from reasoner_runtime.config.models import (
    CallbackProfile,
    ProviderProfile,
    ScrubRuleSet,
)
from reasoner_runtime.core.models import ReasonerRequest, StructuredGenerationResult
from reasoner_runtime.providers import (
    ParseValidationError,
    build_client,
    execute_with_fallback,
)
from reasoner_runtime.replay import (
    ReplayBundle,
    build_llm_lineage,
    build_replay_bundle,
)
from reasoner_runtime.scrub import scrub_request
from reasoner_runtime.structured import resolve_response_model, run_structured_call


ClientFactory = Callable[[ProviderProfile, int], Any]
_INSTRUCTOR_ATTEMPTS_PER_FALLBACK_RETRY = 1
_RUNTIME_CALLBACK_LOCK = RLock()


def generate_structured(
    request: ReasonerRequest,
    *,
    schema_registry: Mapping[str, type[BaseModel]],
    provider_profiles: list[ProviderProfile] | None = None,
    provider_config_path: Path | None = None,
    client_factory: ClientFactory = build_client,
    scrub_rule_set: ScrubRuleSet | None = None,
    callback_profile: CallbackProfile | None = None,
    callback_config_path: Path | None = None,
) -> StructuredGenerationResult:
    """Generate structured output through the configured provider boundary.

    Callers may inject provider profiles directly or load them from a config
    path. Without either, the configured request target is converted into a
    single profile to preserve the provider boundary.
    """
    result, _bundle = _generate_structured_with_replay_impl(
        request,
        schema_registry=schema_registry,
        provider_profiles=provider_profiles,
        provider_config_path=provider_config_path,
        client_factory=client_factory,
        scrub_rule_set=scrub_rule_set,
        callback_profile=callback_profile,
        callback_config_path=callback_config_path,
    )
    return result


def generate_structured_with_replay(
    request: ReasonerRequest,
    provider_profiles: list[ProviderProfile] | None = None,
    schema_registry: Mapping[str, type[BaseModel]] | None = None,
    client_factory: ClientFactory = build_client,
    *,
    provider_config_path: Path | None = None,
    scrub_rule_set: ScrubRuleSet | None = None,
    callback_profile: CallbackProfile | None = None,
    callback_config_path: Path | None = None,
) -> tuple[StructuredGenerationResult, ReplayBundle]:
    if schema_registry is None:
        raise TypeError("schema_registry is required")

    return _generate_structured_with_replay_impl(
        request,
        schema_registry=schema_registry,
        provider_profiles=provider_profiles,
        provider_config_path=provider_config_path,
        client_factory=client_factory,
        scrub_rule_set=scrub_rule_set,
        callback_profile=callback_profile,
        callback_config_path=callback_config_path,
    )


def _generate_structured_with_replay_impl(
    request: ReasonerRequest,
    *,
    schema_registry: Mapping[str, type[BaseModel]],
    provider_profiles: list[ProviderProfile] | None,
    provider_config_path: Path | None,
    client_factory: ClientFactory,
    scrub_rule_set: ScrubRuleSet | None,
    callback_profile: CallbackProfile | None,
    callback_config_path: Path | None,
) -> tuple[StructuredGenerationResult, ReplayBundle]:
    normalized_request = _normalize_request(request)
    profiles = _resolve_provider_profiles(
        normalized_request,
        provider_profiles=provider_profiles,
        provider_config_path=provider_config_path,
    )
    with _RUNTIME_CALLBACK_LOCK:
        try:
            _configure_runtime_callbacks(
                callback_profile=callback_profile,
                callback_config_path=callback_config_path,
            )

            scrubbed = scrub_request(
                normalized_request.messages,
                normalized_request.metadata,
                scrub_rule_set,
            )
            runtime_request = normalized_request.model_copy(
                update={"messages": scrubbed.messages, "metadata": scrubbed.metadata}
            )

            response_model = resolve_response_model(
                normalized_request.target_schema,
                schema_registry,
            )
            final_raw_output: str | None = None

            def call_provider(
                call_request: ReasonerRequest,
                profile: ProviderProfile,
                parse_retry_index: int,
            ) -> StructuredGenerationResult:
                nonlocal final_raw_output

                if parse_retry_index < 0:
                    raise ValueError(
                        "parse_retry_index must be greater than or equal to 0"
                    )

                # execute_with_fallback owns request.max_retries; Instructor
                # gets one attempt.
                client = client_factory(
                    profile,
                    _INSTRUCTOR_ATTEMPTS_PER_FALLBACK_RETRY,
                )
                try:
                    call_result = run_structured_call(
                        client,
                        call_request,
                        response_model,
                    )
                except Exception as error:
                    parse_error = _parse_error_from_instructor_retry(error)
                    if parse_error is not None:
                        raise parse_error from error
                    raise
                final_raw_output = call_result.raw_output

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
                runtime_request,
                profiles,
                call_provider,
            )
            if final_raw_output is None:
                raise RuntimeError("structured call did not produce raw output")

            lineage = build_llm_lineage(result)
            replay_bundle = build_replay_bundle(
                scrubbed.sanitized_input,
                final_raw_output,
                result.parsed_result,
                lineage,
            )
            return result, replay_bundle
        finally:
            configure_litellm_callbacks(())


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


def _configure_runtime_callbacks(
    *,
    callback_profile: CallbackProfile | None,
    callback_config_path: Path | None,
) -> None:
    if callback_profile is not None and callback_config_path is not None:
        raise ValueError(
            "callback_profile and callback_config_path cannot both be provided"
        )

    resolved_profile = (
        load_callback_profile(callback_config_path)
        if callback_config_path is not None
        else callback_profile
    )
    backends = build_callback_backends(resolved_profile)
    configure_litellm_callbacks(backends)


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


def _parse_error_from_instructor_retry(error: Exception) -> ParseValidationError | None:
    retry_exception_type = _instructor_retry_exception_type()
    if retry_exception_type is None or not isinstance(error, retry_exception_type):
        return None

    failed_attempts = getattr(error, "failed_attempts", None)
    if not failed_attempts:
        return None

    if not all(
        _is_instructor_parse_failure(getattr(attempt, "exception", None))
        for attempt in failed_attempts
    ):
        return None

    return ParseValidationError(str(error))


def _is_instructor_parse_failure(error: Any) -> bool:
    if isinstance(
        error,
        (ParseValidationError, PydanticValidationError, JSONDecodeError),
    ):
        return True

    instructor_validation_error_type = _instructor_validation_error_type()
    return instructor_validation_error_type is not None and isinstance(
        error,
        instructor_validation_error_type,
    )


def _instructor_retry_exception_type() -> type[Exception] | None:
    try:
        from instructor.core import InstructorRetryException
    except ImportError:
        return None

    return InstructorRetryException


def _instructor_validation_error_type() -> type[Exception] | None:
    try:
        from instructor.core import ValidationError
    except ImportError:
        return None

    return ValidationError
