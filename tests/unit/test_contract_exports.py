from __future__ import annotations

from contracts.schemas import (
    ReasonerErrorCategory,
    ReasonerHealth as ContractReasonerHealth,
    ReasonerReplay as ContractReasonerReplay,
    ReasonerRequest as ContractReasonerRequest,
    ReasonerResult as ContractReasonerResult,
)

from reasoner_runtime.core import ReasonerRequest, StructuredGenerationResult
from reasoner_runtime.health import (
    HealthCheckReport,
    ProviderHealthStatus,
    QuotaStatus,
    aggregate_health_statuses,
)
from reasoner_runtime.providers import FailureClass
from reasoner_runtime.replay import ReplayBundle


def test_public_runtime_models_are_contract_backed() -> None:
    assert issubclass(ReasonerRequest, ContractReasonerRequest)
    assert issubclass(StructuredGenerationResult, ContractReasonerResult)
    assert issubclass(ReplayBundle, ContractReasonerReplay)
    assert issubclass(HealthCheckReport, ContractReasonerHealth)


def test_runtime_request_exports_stable_contract_projection() -> None:
    request = ReasonerRequest(
        request_id="req-contract",
        caller_module="entity-registry",
        target_schema="EntityResult",
        messages=[{"role": "user", "content": "resolve Apple"}],
        configured_provider="openai",
        configured_model="gpt-5.4",
        max_retries=2,
        metadata={"cycle_id": "cycle-1", "entity": "AAPL"},
    )

    contract = request.to_contract()

    assert type(contract) is ContractReasonerRequest
    assert contract.request_id == "req-contract"
    assert contract.cycle_id == "cycle-1"
    assert contract.reasoner_name == "entity-registry"
    assert contract.prompt == "resolve Apple"
    assert contract.context == {"cycle_id": "cycle-1", "entity": "AAPL"}


def test_replay_bundle_preserves_core_fields_and_contract_envelope() -> None:
    bundle = ReplayBundle(
        sanitized_input="hello",
        input_hash="input-hash",
        raw_output='{"answer":"ok"}',
        parsed_result={"answer": "ok"},
        output_hash="output-hash",
        llm_lineage={
            "request_id": "req-1",
            "provider": "openai",
            "model": "gpt-5.4",
            "fallback_path": ["openai/gpt-5.4"],
            "retry_count": 0,
        },
    )

    assert {
        "sanitized_input",
        "input_hash",
        "raw_output",
        "parsed_result",
        "output_hash",
    } <= set(ReplayBundle.model_fields)
    assert set(ContractReasonerReplay.model_fields) <= set(ReplayBundle.model_fields)

    contract = bundle.to_contract()

    assert type(contract) is ContractReasonerReplay
    assert contract.request.request_id == "req-1"
    assert contract.result.output == {"answer": "ok"}


def test_health_report_is_provider_model_contract_structure() -> None:
    report = aggregate_health_statuses(
        [
            ProviderHealthStatus(
                provider="openai",
                model="gpt-5.4",
                reachable=True,
                latency_ms=10,
                quota_status=QuotaStatus.ok,
            ),
            ProviderHealthStatus(
                provider="anthropic",
                model="claude-sonnet-4.5",
                reachable=False,
                latency_ms=20,
                quota_status=QuotaStatus.ok,
                error="connection failed",
            ),
        ]
    )

    contract = report.to_contract()

    assert type(contract) is ContractReasonerHealth
    assert [(item.provider, item.model) for item in report.provider_statuses] == [
        ("openai", "gpt-5.4"),
        ("anthropic", "claude-sonnet-4.5"),
    ]
    assert report.all_critical_targets_available is False
    assert contract.subsystem_id == "reasoner-runtime"
    assert contract.pending_count == 1
    assert contract.error_classification is not None
    assert (
        contract.error_classification.category
        is ReasonerErrorCategory.MODEL_PROVIDER
    )


def test_failed_structured_result_projects_contract_error_classification() -> None:
    result = StructuredGenerationResult(
        status="failed",
        failure_class=FailureClass.task_level,
        parsed_result={},
        actual_provider="openai",
        actual_model="gpt-5.4",
        token_usage={"prompt": 0, "completion": 0, "total": 0},
        cost_estimate=0,
        latency_ms=0,
    )

    contract = result.to_contract()

    assert type(contract) is ContractReasonerResult
    assert contract.status.value == "failed"
    assert contract.error_classification is not None
    assert (
        contract.error_classification.category
        is ReasonerErrorCategory.INPUT_CONTRACT
    )
