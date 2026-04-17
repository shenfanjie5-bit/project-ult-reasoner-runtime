from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class QuotaStatus(str, Enum):
    ok = "ok"
    limited = "limited"
    exhausted = "exhausted"


class ProviderHealthStatus(BaseModel):
    provider: str
    model: str
    reachable: bool
    latency_ms: int = Field(ge=0)
    quota_status: QuotaStatus
    error: str | None = None


class HealthCheckReport(BaseModel):
    provider_statuses: list[ProviderHealthStatus]
    all_critical_targets_available: bool
    summary: str
