from __future__ import annotations

import inspect

import pytest
from pydantic import ValidationError

from reasoner_runtime.config.models import ProviderProfile
from reasoner_runtime.providers import (
    FailureClass,
    build_client,
    classify_failure,
    select_provider,
)


def _profile(
    provider: str = "openai",
    model: str = "gpt-4",
    fallback_priority: int = 0,
) -> ProviderProfile:
    return ProviderProfile(
        provider=provider,
        model=model,
        fallback_priority=fallback_priority,
    )


def test_build_client_requires_max_retries_argument() -> None:
    with pytest.raises(TypeError):
        build_client(_profile())  # type: ignore[call-arg]


def test_build_client_signature_has_no_max_retries_default() -> None:
    signature = inspect.signature(build_client)

    assert signature.parameters["max_retries"].default is inspect.Parameter.empty


def test_build_client_rejects_negative_max_retries() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        build_client(_profile(), -1)


def test_build_client_returns_profile_and_max_retries_config() -> None:
    profile = _profile(provider="anthropic", model="claude-sonnet-4.5")

    client = build_client(profile, 2)

    assert client == {"profile": profile, "max_retries": 2}


def test_select_provider_returns_exact_match() -> None:
    exact = _profile(
        provider="anthropic",
        model="claude-sonnet-4.5",
        fallback_priority=5,
    )
    profiles = [
        _profile(provider="openai", model="gpt-4", fallback_priority=0),
        exact,
    ]

    assert select_provider("anthropic", "claude-sonnet-4.5", profiles) == exact


def test_select_provider_chooses_lowest_priority_exact_match() -> None:
    high_priority = _profile(provider="openai", model="gpt-4", fallback_priority=10)
    low_priority = _profile(provider="openai", model="gpt-4", fallback_priority=1)

    selected = select_provider("openai", "gpt-4", [high_priority, low_priority])

    assert selected == low_priority


def test_select_provider_falls_back_to_lowest_priority_profile() -> None:
    first_fallback = _profile(
        provider="anthropic",
        model="claude-sonnet-4.5",
        fallback_priority=1,
    )
    profiles = [
        _profile(provider="openai", model="gpt-4", fallback_priority=3),
        first_fallback,
    ]

    assert select_provider("missing", "missing-model", profiles) == first_fallback


def test_select_provider_rejects_empty_profiles() -> None:
    with pytest.raises(ValueError, match="provider profile"):
        select_provider("openai", "gpt-4", [])


def test_classify_failure_marks_connection_error_as_infra_level() -> None:
    assert (
        classify_failure(ConnectionError("network down"), {})
        is FailureClass.infra_level
    )


def test_classify_failure_marks_timeout_error_as_infra_level() -> None:
    assert classify_failure(TimeoutError("timed out"), {}) is FailureClass.infra_level


def test_classify_failure_marks_value_error_as_task_level() -> None:
    assert classify_failure(ValueError("bad parse"), {}) is FailureClass.task_level


def test_classify_failure_marks_validation_error_as_task_level() -> None:
    try:
        ProviderProfile(provider="openai")
    except ValidationError as error:
        classified = classify_failure(error, {})

    assert classified is FailureClass.task_level


def test_classify_failure_defaults_unknown_errors_to_infra_level() -> None:
    assert classify_failure(RuntimeError("unknown"), {}) is FailureClass.infra_level
