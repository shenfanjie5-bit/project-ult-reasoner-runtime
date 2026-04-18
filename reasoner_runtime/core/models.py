from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, TypeVar

from reasoner_runtime._contracts import ensure_contracts_importable

ensure_contracts_importable()

from contracts.schemas.reasoner import (
    ReasonerRequest as ContractReasonerRequest,
    ReasonerResult as ContractReasonerResult,
)
from pydantic import BaseModel, Field, model_validator


NonNegativeInt = Annotated[int, Field(ge=0)]
_RUNTIME_CONTRACT_VERSION = "0.1.0"
ContractModelT = TypeVar("ContractModelT", bound=BaseModel)


def _prompt_from_messages(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for message in messages:
        content = message.get("content")
        if content is None:
            continue
        parts.append(str(content))

    return "\n".join(parts)


def _contract_projection(
    model: BaseModel,
    contract_model: type[ContractModelT],
) -> ContractModelT:
    return contract_model.model_validate(
        model.model_dump(include=set(contract_model.model_fields))
    )


class ReasonerRequest(ContractReasonerRequest):
    request_id: str
    caller_module: str
    target_schema: str
    messages: list[dict[str, Any]]
    configured_provider: str
    configured_model: str
    max_retries: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def populate_contract_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        values = dict(data)
        metadata = values.get("metadata")
        context = dict(metadata) if isinstance(metadata, dict) else {}
        messages = values.get("messages")
        prompt = _prompt_from_messages(messages) if isinstance(messages, list) else ""
        caller_module = str(values.get("caller_module", "")).strip()

        values.setdefault("cycle_id", str(context.get("cycle_id", "runtime-cycle")))
        values.setdefault(
            "reasoner_name",
            caller_module or "reasoner-runtime",
        )
        values.setdefault(
            "reasoner_version",
            str(context.get("reasoner_version", _RUNTIME_CONTRACT_VERSION)),
        )
        values.setdefault(
            "prompt",
            prompt or str(values.get("target_schema", "reasoner-runtime")),
        )
        values.setdefault("context", context)
        values.setdefault("requested_at", datetime.now(UTC))
        return values

    def to_contract(self) -> ContractReasonerRequest:
        return _contract_projection(self, ContractReasonerRequest)


class StructuredGenerationResult(ContractReasonerResult):
    parsed_result: dict[str, Any]
    actual_provider: str
    actual_model: str
    fallback_path: list[str] = Field(default_factory=list)
    retry_count: int = Field(default=0, ge=0)
    token_usage: dict[str, NonNegativeInt]
    cost_estimate: float = Field(ge=0)
    latency_ms: int = Field(ge=0)

    @model_validator(mode="before")
    @classmethod
    def populate_contract_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        values = dict(data)
        parsed_result = values.get("parsed_result")
        output = parsed_result if isinstance(parsed_result, dict) else {}

        values.setdefault("result_id", "runtime-result")
        values.setdefault("request_id", "runtime-request")
        values.setdefault("status", "completed")
        values.setdefault("reasoner_name", "reasoner-runtime")
        values.setdefault("reasoner_version", _RUNTIME_CONTRACT_VERSION)
        values.setdefault("output", output)
        values.setdefault("completed_at", datetime.now(UTC))
        return values

    def to_contract(self) -> ContractReasonerResult:
        return _contract_projection(self, ContractReasonerResult)
