from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from reasoner_runtime.config.models import ProviderProfile
from reasoner_runtime.providers.models import FailureClass


def select_provider(
    configured_provider: str,
    configured_model: str,
    profiles: list[ProviderProfile],
) -> ProviderProfile:
    if not profiles:
        raise ValueError("at least one provider profile is required")

    sorted_profiles = sorted(profiles, key=lambda profile: profile.fallback_priority)
    for profile in sorted_profiles:
        if (
            profile.provider == configured_provider
            and profile.model == configured_model
        ):
            return profile

    return sorted_profiles[0]


def classify_failure(error: Exception, context: dict[str, Any]) -> FailureClass:
    _ = context
    if isinstance(error, (ConnectionError, TimeoutError)):
        return FailureClass.infra_level
    if isinstance(error, (ValueError, ValidationError)):
        return FailureClass.task_level
    return FailureClass.infra_level
