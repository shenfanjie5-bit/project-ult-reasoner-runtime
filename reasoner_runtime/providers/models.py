from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class FailureClass(str, Enum):
    none = "none"
    success_with_fallback = "success_with_fallback"
    task_level = "task_level"
    infra_level = "infra_level"


class FallbackDecision(BaseModel):
    configured_target: str
    attempts: list[str] = Field(default_factory=list)
    final_target: str | None = None
    failure_class: FailureClass = FailureClass.none
    terminal_reason: str | None = None
