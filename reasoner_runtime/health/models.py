from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class QuotaStatus(str, Enum):
    ok = "ok"
    limited = "limited"
    exhausted = "exhausted"


class ProviderHealthStatus(BaseModel):
    provider: str
    model: str
    reachable: bool
    latency_ms: int
    quota_status: QuotaStatus
    error: str | None = None
