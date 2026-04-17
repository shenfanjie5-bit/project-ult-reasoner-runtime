from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, Field


NonNegativeInt = Annotated[int, Field(ge=0)]


class ReasonerRequest(BaseModel):
    request_id: str
    caller_module: str
    target_schema: str
    messages: list[dict[str, Any]]
    configured_provider: str
    configured_model: str
    max_retries: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StructuredGenerationResult(BaseModel):
    parsed_result: dict[str, Any]
    actual_provider: str
    actual_model: str
    fallback_path: list[str] = Field(default_factory=list)
    retry_count: int = Field(default=0, ge=0)
    token_usage: dict[str, NonNegativeInt]
    cost_estimate: float = Field(ge=0)
    latency_ms: int = Field(ge=0)
