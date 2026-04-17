from __future__ import annotations

from reasoner_runtime.config import ProviderProfile
from reasoner_runtime.health import ProviderHealthStatus, QuotaStatus, health_check


def test_health_check_reports_multiple_provider_model_combinations() -> None:
    profiles = [
        ProviderProfile(provider="openai", model="gpt-4", timeout_ms=30000),
        ProviderProfile(
            provider="anthropic",
            model="claude-sonnet-4.5",
            timeout_ms=30000,
        ),
    ]
    calls: list[tuple[str, str]] = []

    def fake_probe(
        profile: ProviderProfile,
        timeout_s: float,
    ) -> ProviderHealthStatus:
        calls.append((profile.provider, profile.model))
        return ProviderHealthStatus(
            provider=profile.provider,
            model=profile.model,
            reachable=True,
            latency_ms=10,
            quota_status=QuotaStatus.ok,
        )

    report = health_check(profiles, probe=fake_probe)

    assert calls == [
        ("openai", "gpt-4"),
        ("anthropic", "claude-sonnet-4.5"),
    ]
    assert report.all_critical_targets_available is True
    assert report.model_dump(mode="json") == {
        "provider_statuses": [
            {
                "provider": "openai",
                "model": "gpt-4",
                "reachable": True,
                "latency_ms": 10,
                "quota_status": "ok",
                "error": None,
            },
            {
                "provider": "anthropic",
                "model": "claude-sonnet-4.5",
                "reachable": True,
                "latency_ms": 10,
                "quota_status": "ok",
                "error": None,
            },
        ],
        "all_critical_targets_available": True,
        "summary": "all 2 critical provider/model target(s) available",
    }


def test_health_check_empty_profiles_returns_failing_report() -> None:
    report = health_check([], probe=lambda profile, timeout_s: None)  # type: ignore[arg-type,return-value]

    assert report.provider_statuses == []
    assert report.all_critical_targets_available is False
