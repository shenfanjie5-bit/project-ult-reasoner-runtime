from __future__ import annotations

from time import perf_counter

from reasoner_runtime.core import ReasonerRequest, StructuredGenerationResult
from reasoner_runtime.replay import (
    ReplayBundle,
    build_llm_lineage,
    build_replay_bundle,
    sha256_text,
)


def _result(
    *,
    request_id: str = "req-replay-unit",
    result_id: str = "res-replay-unit",
    reasoner_name: str = "unit-test",
    reasoner_version: str = "0.1.0",
    fallback_path: list[str] | None = None,
    retry_count: int = 0,
) -> StructuredGenerationResult:
    return StructuredGenerationResult(
        result_id=result_id,
        request_id=request_id,
        reasoner_name=reasoner_name,
        reasoner_version=reasoner_version,
        parsed_result={"answer": "ok"},
        actual_provider="openai",
        actual_model="gpt-4",
        fallback_path=fallback_path or [],
        retry_count=retry_count,
        token_usage={"prompt": 1, "completion": 2, "total": 3},
        cost_estimate=0.01,
        latency_ms=5,
    )


def _request() -> ReasonerRequest:
    return ReasonerRequest(
        request_id="req-replay-unit",
        caller_module="unit-test",
        target_schema="ReplayPayload",
        messages=[{"role": "user", "content": "return a replay payload"}],
        configured_provider="openai",
        configured_model="gpt-4",
        max_retries=2,
    )


def test_sha256_text_hashes_utf8_text() -> None:
    assert (
        sha256_text("hello")
        == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )


def test_sha256_text_hashes_empty_string() -> None:
    assert (
        sha256_text("")
        == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_build_llm_lineage_reads_fields_from_result() -> None:
    lineage = build_llm_lineage(
        _result(
            fallback_path=["openai/gpt-4", "anthropic/claude-sonnet-4.5"],
            retry_count=2,
        )
    )

    assert lineage == {
        "provider": "openai",
        "model": "gpt-4",
        "fallback_path": ["openai/gpt-4", "anthropic/claude-sonnet-4.5"],
        "retry_count": 2,
    }


def test_build_llm_lineage_keeps_primary_path_as_list() -> None:
    lineage = build_llm_lineage(_result())

    assert lineage["fallback_path"] == []


def test_build_replay_bundle_populates_core_five_fields_and_lineage() -> None:
    parsed_result = {"answer": "ok", "score": 1}
    request = _request()
    result = _result(
        request_id=request.request_id,
        reasoner_name=request.reasoner_name,
        reasoner_version=request.reasoner_version,
        fallback_path=["openai/gpt-4"],
    )
    lineage = build_llm_lineage(result)

    bundle = build_replay_bundle(
        request,
        result,
        "sanitized input",
        '{"answer":"ok","score":1}',
        parsed_result,
        lineage,
    )

    assert isinstance(bundle, ReplayBundle)
    assert bundle.sanitized_input == "sanitized input"
    assert bundle.input_hash == sha256_text("sanitized input")
    assert bundle.raw_output == '{"answer":"ok","score":1}'
    assert bundle.parsed_result == parsed_result
    assert bundle.output_hash == sha256_text('{"answer":"ok","score":1}')
    assert bundle.llm_lineage == lineage
    assert bundle.request.request_id == request.request_id
    assert bundle.result.request_id == request.request_id


def test_build_replay_bundle_preserves_raw_output_without_normalizing() -> None:
    raw_output = ' \n{"b":2,"a":1}\n '
    request = _request()

    bundle = build_replay_bundle(
        request,
        _result(request_id=request.request_id),
        "in",
        raw_output,
        {"a": 1, "b": 2},
        {},
    )

    assert bundle.raw_output == raw_output
    assert bundle.output_hash == sha256_text(raw_output)


def test_build_replay_bundle_runtime_baseline_under_100ms() -> None:
    request = _request()
    result = _result(request_id=request.request_id)
    build_replay_bundle(request, result, "warmup", "{}", {}, {})

    started_at = perf_counter()
    build_replay_bundle(
        request,
        result,
        "input",
        '{"answer":"ok"}',
        {"answer": "ok"},
        {},
    )
    elapsed_ms = (perf_counter() - started_at) * 1000

    assert elapsed_ms < 100
