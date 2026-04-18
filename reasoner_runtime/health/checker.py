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
from reasoner_runtime.providers.client import build_litellm_completion_kwargs
from reasoner_runtime.providers.models import provider_quota_status_from_error
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
            **build_litellm_completion_kwargs(
                profile,
                messages=[{"role": "user", "content": "health check"}],
                max_tokens=1,
                timeout_s=timeout_s,
            )
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


def _quota_status_from_error(
    error: Exception | None,
    reachable: bool,
) -> QuotaStatus:
    if error is None and reachable:
        return QuotaStatus.ok
    if error is None:
        return QuotaStatus.ok

    return QuotaStatus(provider_quota_status_from_error(error))


def _safe_error_summary(error: Exception) -> str:
    raw_summary = f"{type(error).__name__}: {error}"
    scrubbed = scrub_text(raw_summary).replace("\n", " ").replace("\r", " ")
    if len(scrubbed) <= _ERROR_SUMMARY_LIMIT:
        return scrubbed

    return scrubbed[: _ERROR_SUMMARY_LIMIT - 3].rstrip() + "..."
