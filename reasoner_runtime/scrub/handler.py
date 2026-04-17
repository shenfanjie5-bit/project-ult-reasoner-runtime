from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from reasoner_runtime.config.models import ScrubRuleSet
from reasoner_runtime.scrub.rules import scrub_text


@dataclass(frozen=True)
class ScrubbedRequest:
    messages: list[dict[str, Any]]
    metadata: dict[str, Any]
    sanitized_input: str


def scrub_payload(value: Any, rule_set: ScrubRuleSet | None = None) -> Any:
    if isinstance(value, str):
        return scrub_text(value, rule_set)
    if isinstance(value, dict):
        return {key: scrub_payload(item, rule_set) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub_payload(item, rule_set) for item in value]
    if isinstance(value, tuple):
        return tuple(scrub_payload(item, rule_set) for item in value)

    return value


def scrub_request(
    messages: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
    rule_set: ScrubRuleSet | None = None,
) -> ScrubbedRequest:
    scrubbed_messages = cast(list[dict[str, Any]], scrub_payload(messages, rule_set))
    scrubbed_metadata = cast(dict[str, Any], scrub_payload(metadata or {}, rule_set))
    sanitized_input = json.dumps(
        {
            "messages": scrubbed_messages,
            "metadata": scrubbed_metadata,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return ScrubbedRequest(
        messages=scrubbed_messages,
        metadata=scrubbed_metadata,
        sanitized_input=sanitized_input,
    )


def scrub_input(
    messages: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
    rule_set: ScrubRuleSet | None = None,
) -> str:
    return scrub_request(messages, metadata, rule_set).sanitized_input


__all__ = [
    "ScrubbedRequest",
    "scrub_input",
    "scrub_payload",
    "scrub_request",
]
