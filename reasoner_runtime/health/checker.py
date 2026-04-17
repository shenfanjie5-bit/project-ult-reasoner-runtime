from __future__ import annotations

from collections.abc import Callable
from time import perf_counter

from reasoner_runtime.config.models import ProviderProfile
from reasoner_runtime.health.aggregator import aggregate_health_statuses
from reasoner_runtime.health.models import (
    HealthCheckReport,
    ProviderHealthStatus,
    QuotaStatus,
)
from reasoner_runtime.providers.client import _litellm_model_name
from reasoner_runtime.scrub import scrub_text


HealthProbe = Callable[[ProviderProfile, float], ProviderHealthStatus]

_ERROR_SUMMARY_LIMIT = 240


def health_check(
    provider_profiles: list[ProviderProfile],
    *,
    probe: HealthProbe | None = None,
    timeout_s: float = 3.0,
) -> HealthCheckReport:
    probe_fn = probe or probe_provider
    statuses: list[ProviderHealthStatus] = []

    for profile in provider_profiles:
        started_at = perf_counter()
        try:
            status = probe_fn(profile, timeout_s)
        except Exception as error:
            latency_ms = int((perf_counter() - started_at) * 1000)
            status = ProviderHealthStatus(
                provider=profile.provider,
                model=profile.model,
                reachable=False,
                latency_ms=max(latency_ms, 0),
                quota_status=_quota_status_from_error(error, reachable=False),
                error=_safe_error_summary(error),
            )
        else:
            status = status.model_copy(
                update={
                    "provider": profile.provider,
                    "model": profile.model,
                }
            )
        statuses.append(status)

    return aggregate_health_statuses(statuses)


def probe_provider(
    profile: ProviderProfile,
    timeout_s: float = 3.0,
) -> ProviderHealthStatus:
    started_at = perf_counter()
    try:
        from litellm import completion

        completion(
            model=_litellm_model_name(profile),
            messages=[{"role": "user", "content": "health check"}],
            max_tokens=1,
            timeout=_effective_timeout_s(profile, timeout_s),
        )
    except Exception as error:
        latency_ms = int((perf_counter() - started_at) * 1000)
        return ProviderHealthStatus(
            provider=profile.provider,
            model=profile.model,
            reachable=False,
            latency_ms=max(latency_ms, 0),
            quota_status=_quota_status_from_error(error, reachable=False),
            error=_safe_error_summary(error),
        )

    latency_ms = int((perf_counter() - started_at) * 1000)
    return ProviderHealthStatus(
        provider=profile.provider,
        model=profile.model,
        reachable=True,
        latency_ms=max(latency_ms, 0),
        quota_status=QuotaStatus.ok,
    )


def _effective_timeout_s(profile: ProviderProfile, timeout_s: float) -> float:
    return min(timeout_s, profile.timeout_ms / 1000)


def _quota_status_from_error(
    error: Exception | None,
    reachable: bool,
) -> QuotaStatus:
    if error is None and reachable:
        return QuotaStatus.ok
    if error is None:
        return QuotaStatus.ok

    class_names = " ".join(cls.__name__.lower() for cls in type(error).mro())
    message = str(error).lower()
    combined = f"{class_names} {message}"

    exhausted_markers = (
        "authenticationerror",
        "auth",
        "unauthorized",
        "forbidden",
        "invalid api key",
        "api key",
        "budgetexceeded",
        "budget exceeded",
        "quotaexceeded",
        "quota exceeded",
        "quota exhausted",
        "insufficient_quota",
        "billing",
        "credits exhausted",
    )
    limited_markers = (
        "ratelimiterror",
        "rate limit",
        "rate_limit",
        "too many requests",
        "limited",
        " 429",
    )

    if any(marker in combined for marker in exhausted_markers):
        return QuotaStatus.exhausted
    if any(marker in combined for marker in limited_markers):
        return QuotaStatus.limited

    return QuotaStatus.ok


def _safe_error_summary(error: Exception) -> str:
    raw_summary = f"{type(error).__name__}: {error}"
    scrubbed = scrub_text(raw_summary).replace("\n", " ").replace("\r", " ")
    if len(scrubbed) <= _ERROR_SUMMARY_LIMIT:
        return scrubbed

    return scrubbed[: _ERROR_SUMMARY_LIMIT - 3].rstrip() + "..."
