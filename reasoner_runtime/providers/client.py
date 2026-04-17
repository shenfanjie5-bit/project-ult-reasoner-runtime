from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from reasoner_runtime.config.models import ProviderProfile
from reasoner_runtime.providers.routing import ProviderConfigError


@dataclass(frozen=True)
class LiteLLMInstructorClient:
    profile: ProviderProfile
    max_retries: int
    litellm_model: str
    instructor_client: Any

    def create_structured(
        self,
        *,
        messages: list[dict[str, Any]],
        response_model: type[Any],
    ) -> Any:
        kwargs = {
            "model": self.litellm_model,
            "messages": messages,
            "response_model": response_model,
            "max_retries": self.max_retries,
            "timeout": self.profile.timeout_ms / 1000,
        }

        completions = self.instructor_client.chat.completions
        if hasattr(completions, "create_with_completion"):
            return completions.create_with_completion(**kwargs)

        return completions.create(**kwargs)


def build_client(profile: ProviderProfile, max_retries: int) -> Any:
    if max_retries < 0:
        raise ValueError("max_retries must be greater than or equal to 0")

    litellm_model = _litellm_model_name(profile)

    return LiteLLMInstructorClient(
        profile=profile,
        max_retries=max_retries,
        litellm_model=litellm_model,
        instructor_client=_create_instructor_client(),
    )


def _create_instructor_client() -> Any:
    try:
        import instructor
        from litellm import completion
    except ImportError as error:
        raise ProviderConfigError(
            "litellm and instructor must be installed to build a provider client"
        ) from error

    return instructor.from_litellm(completion)


def _litellm_model_name(profile: ProviderProfile) -> str:
    if "/" in profile.model:
        provider_prefix, _, _ = profile.model.partition("/")
        if provider_prefix != profile.provider:
            raise ProviderConfigError(
                "profile.model provider prefix must match profile.provider: "
                f"{profile.model!r} conflicts with {profile.provider!r}"
            )
        return profile.model

    return f"{profile.provider}/{profile.model}"
