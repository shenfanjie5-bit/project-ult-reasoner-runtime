from __future__ import annotations

import hashlib
from time import perf_counter
from typing import Any

from reasoner_runtime.core import StructuredGenerationResult
from reasoner_runtime.replay import (
    ReplayBundle,
    build_llm_lineage,
    build_replay_bundle,
    sha256_text,
)


def _result(**overrides: Any) -> StructuredGenerationResult:
    payload = {
        "parsed_result": {"answer": "ok"},
        "actual_provider": "openai",
        "actual_model": "gpt-4",
        "fallback_path": ["openai/gpt-4"],
        "retry_count": 1,
        "token_usage": {"prompt": 1, "completion": 2, "total": 3},
        "cost_estimate": 0.01,
        "latency_ms": 10,
    }
    payload.update(overrides)
    return StructuredGenerationResult(**payload)


def test_sha256_text_matches_utf8_hashlib() -> None:
    value = "hello"

    assert sha256_text(value) == hashlib.sha256(value.encode("utf-8")).hexdigest()


def test_sha256_text_hashes_empty_string() -> None:
    assert (
        sha256_text("")
        == "e3b0c44298fc1c149afbf4c8996fb924"
        "27ae41e4649b934ca495991b7852b855"
    )


def test_build_llm_lineage_uses_structured_generation_result_fields() -> None:
    result = _result(
        actual_provider="anthropic",
        actual_model="claude-sonnet-4.5",
        fallback_path=["openai/gpt-4", "anthropic/claude-sonnet-4.5"],
        retry_count=3,
    )

    lineage = build_llm_lineage(result)

    assert lineage == {
        "provider": "anthropic",
        "model": "claude-sonnet-4.5",
        "fallback_path": ["openai/gpt-4", "anthropic/claude-sonnet-4.5"],
        "retry_count": 3,
    }


def test_build_llm_lineage_keeps_fallback_path_as_explicit_list() -> None:
    lineage = build_llm_lineage(_result(fallback_path=[]))

    assert lineage["fallback_path"] == []


def test_build_replay_bundle_populates_core_five_fields_and_lineage() -> None:
    sanitized_input = '[{"content":"hello","role":"user"}]'
    raw_output = '{"answer":"ok"}'
    parsed_result = {"answer": "ok"}
    lineage = {
        "provider": "openai",
        "model": "gpt-4",
        "fallback_path": ["openai/gpt-4"],
        "retry_count": 0,
    }

    bundle = build_replay_bundle(
        sanitized_input,
        raw_output,
        parsed_result,
        lineage,
    )

    assert isinstance(bundle, ReplayBundle)
    assert bundle.sanitized_input == sanitized_input
    assert bundle.input_hash == sha256_text(sanitized_input)
    assert bundle.raw_output == raw_output
    assert bundle.parsed_result == parsed_result
    assert bundle.output_hash == sha256_text(raw_output)
    assert bundle.llm_lineage == lineage


def test_build_replay_bundle_preserves_raw_output_without_normalization() -> None:
    raw_output = ' \n{"b":2,"a":1}\n '

    bundle = build_replay_bundle(
        "input",
        raw_output,
        {"b": 2, "a": 1},
        {
            "provider": "openai",
            "model": "gpt-4",
            "fallback_path": [],
            "retry_count": 0,
        },
    )

    assert bundle.raw_output == raw_output
    assert bundle.output_hash == sha256_text(raw_output)


def test_build_replay_bundle_completes_under_performance_baseline() -> None:
    started_at = perf_counter()

    build_replay_bundle(
        "input",
        "output",
        {"ok": True},
        {
            "provider": "openai",
            "model": "gpt-4",
            "fallback_path": [],
            "retry_count": 0,
        },
    )

    elapsed_ms = (perf_counter() - started_at) * 1000
    assert elapsed_ms < 100
