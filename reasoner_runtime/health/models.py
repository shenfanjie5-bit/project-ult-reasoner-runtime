from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from reasoner_runtime._contracts import ensure_contracts_importable

ensure_contracts_importable()

from contracts.core import HeartbeatStatus
from contracts.schemas.reasoner import ReasonerHealth as ContractReasonerHealth
from pydantic import BaseModel, Field, model_validator

from reasoner_runtime.core.models import (
    _RUNTIME_CONTRACT_VERSION,
    _contract_projection,
)


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


class HealthCheckReport(ContractReasonerHealth):
    provider_statuses: list[ProviderHealthStatus]
    all_critical_targets_available: bool
    summary: str

    @model_validator(mode="before")
    @classmethod
    def populate_contract_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        values = dict(data)
        statuses = values.get("provider_statuses")
        provider_statuses = statuses if isinstance(statuses, list) else []
        checked_at = values.get("checked_at", datetime.now(UTC))
        all_available = bool(values.get("all_critical_targets_available", False))
        unavailable_count = sum(
            1 for status in provider_statuses if _provider_status_unavailable(status)
        )

        values.setdefault("subsystem_id", "reasoner-runtime")
        values.setdefault("version", _RUNTIME_CONTRACT_VERSION)
        values.setdefault("checked_at", checked_at)
        values.setdefault(
            "status",
            HeartbeatStatus.OK if all_available else HeartbeatStatus.DEGRADED,
        )
        values.setdefault("last_success_at", checked_at if all_available else None)
        values.setdefault("pending_count", unavailable_count)
        return values

    def to_contract(self) -> ContractReasonerHealth:
        return _contract_projection(self, ContractReasonerHealth)


def _provider_status_unavailable(status: object) -> bool:
    if isinstance(status, ProviderHealthStatus):
        return not status.reachable or status.quota_status != QuotaStatus.ok
    if isinstance(status, dict):
        return not bool(status.get("reachable", False)) or (
            status.get("quota_status") != QuotaStatus.ok
            and status.get("quota_status") != QuotaStatus.ok.value
        )

    return True
