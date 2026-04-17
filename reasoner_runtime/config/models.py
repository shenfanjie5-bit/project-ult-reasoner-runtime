from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProviderProfile(BaseModel):
    provider: str
    model: str
    timeout_ms: int = 30000
    fallback_priority: int = 0
    rate_limit_rpm: int | None = None


class ScrubRule(BaseModel):
    pattern_type: Literal["name", "phone", "account"]
    enabled: bool = True


class ScrubRuleSet(BaseModel):
    enabled: bool = True
    rules: list[ScrubRule] = Field(default_factory=list)


class CallbackProfile(BaseModel):
    backend: Literal["otel", "langfuse", "none"] = "none"
    endpoint: str | None = None
    enabled: bool = False


class DependencyLockEntry(BaseModel):
    package: str
    version: str
    sha256: str
