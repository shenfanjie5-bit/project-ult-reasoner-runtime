from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from reasoner_runtime._contracts import ensure_contracts_importable

ensure_contracts_importable()

from contracts.schemas.reasoner import ReasonerReplay as ContractReasonerReplay
from pydantic import ConfigDict, Field, model_validator

from reasoner_runtime.core.models import (
    _RUNTIME_CONTRACT_VERSION,
    _contract_projection,
    ReasonerRequest,
    StructuredGenerationResult,
)


class ReplayBundle(ContractReasonerReplay):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=False,
        validate_assignment=True,
    )

    sanitized_input: str
    input_hash: str
    raw_output: str
    parsed_result: dict[str, Any]
    output_hash: str
    llm_lineage: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def populate_contract_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        values = dict(data)
        lineage = values.get("llm_lineage")
        lineage = lineage if isinstance(lineage, dict) else {}
        parsed_result = values.get("parsed_result")
        parsed_result = parsed_result if isinstance(parsed_result, dict) else {}

        request_id = str(lineage.get("request_id", "runtime-request"))
        reasoner_name = str(lineage.get("reasoner_name", "reasoner-runtime"))
        reasoner_version = str(
            lineage.get("reasoner_version", _RUNTIME_CONTRACT_VERSION)
        )
        recorded_at = values.get("recorded_at", datetime.now(UTC))

        values.setdefault("replay_id", f"replay-{values.get('input_hash', 'runtime')}")
        values.setdefault(
            "request",
            ReasonerRequest(
                request_id=request_id,
                cycle_id=str(lineage.get("cycle_id", "runtime-cycle")),
                reasoner_name=reasoner_name,
                reasoner_version=reasoner_version,
                prompt=str(values.get("sanitized_input", "runtime replay input")),
                context={"llm_lineage": lineage},
                requested_at=recorded_at,
                caller_module=reasoner_name,
                target_schema=str(lineage.get("target_schema", "parsed_result")),
                messages=[
                    {
                        "role": "user",
                        "content": str(
                            values.get("sanitized_input", "runtime replay input")
                        ),
                    }
                ],
                configured_provider=str(lineage.get("provider", "unknown")),
                configured_model=str(lineage.get("model", "unknown")),
                max_retries=int(lineage.get("retry_count", 0)),
                metadata={"llm_lineage": lineage},
            ).to_contract(),
        )
        values.setdefault(
            "result",
            StructuredGenerationResult(
                result_id=str(lineage.get("result_id", f"{request_id}:result")),
                request_id=request_id,
                reasoner_name=reasoner_name,
                reasoner_version=reasoner_version,
                output=parsed_result,
                completed_at=recorded_at,
                parsed_result=parsed_result,
                actual_provider=str(lineage.get("provider", "unknown")),
                actual_model=str(lineage.get("model", "unknown")),
                fallback_path=list(lineage.get("fallback_path", [])),
                retry_count=int(lineage.get("retry_count", 0)),
                token_usage={},
                cost_estimate=0,
                latency_ms=0,
            ).to_contract(),
        )
        values.setdefault("recorded_at", recorded_at)
        values.setdefault("replay_version", reasoner_version)
        return values

    def to_contract(self) -> ContractReasonerReplay:
        return _contract_projection(self, ContractReasonerReplay)
