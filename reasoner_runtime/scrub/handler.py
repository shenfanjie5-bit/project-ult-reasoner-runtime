from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from reasoner_runtime.config.models import ScrubRuleSet
from reasoner_runtime.scrub.rules import (
    REDACTED_ACCOUNT,
    enabled_rule_types,
    scrub_text,
)


_CHINESE_ACCOUNT_CONTEXT_LABEL = (
    r"(?:账户|账号)(?:[_\s-]*(?:id|number|no\.?|编号|号码|号))?"
)
_ENGLISH_ACCOUNT_CONTEXT_EXACT_LABEL = (
    r"(?:account|acct)(?:[_-](?:id|number|no\.?)|\s+(?:id|number|no\.?))"
)
_ENGLISH_ACCOUNT_CONTEXT_BARE_LABEL = r"(?:account|acct)\b"
_ENGLISH_ACCOUNT_CONTEXT_LABEL = (
    rf"(?:{_ENGLISH_ACCOUNT_CONTEXT_EXACT_LABEL}|"
    rf"{_ENGLISH_ACCOUNT_CONTEXT_BARE_LABEL})"
)
_ACCOUNT_CONTEXT_KEY_PATTERN = re.compile(
    rf"^\s*(?:{_CHINESE_ACCOUNT_CONTEXT_LABEL}|"
    rf"\b{_ENGLISH_ACCOUNT_CONTEXT_LABEL})\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ScrubbedRequest:
    messages: list[dict[str, Any]]
    metadata: dict[str, Any]
    sanitized_input: str


def scrub_payload(value: Any, rule_set: ScrubRuleSet | None = None) -> Any:
    account_rule_enabled = "account" in enabled_rule_types(rule_set)
    return _scrub_payload(
        value,
        rule_set,
        account_rule_enabled=account_rule_enabled,
        redact_account_value=False,
    )


def _scrub_payload(
    value: Any,
    rule_set: ScrubRuleSet | None,
    *,
    account_rule_enabled: bool,
    redact_account_value: bool,
) -> Any:
    if redact_account_value and account_rule_enabled:
        if isinstance(value, str) or _is_numeric_account_value(value):
            return REDACTED_ACCOUNT

    if isinstance(value, str):
        return scrub_text(value, rule_set)
    if isinstance(value, dict):
        scrubbed: dict[Any, Any] = {}
        for key, item in value.items():
            scrubbed_key = scrub_text(key, rule_set) if isinstance(key, str) else key
            redact_child_account_value = (
                redact_account_value
                or (
                    account_rule_enabled
                    and isinstance(key, str)
                    and _is_account_context_key(key, scrubbed_key)
                )
            )
            output_key = _unique_scrubbed_key(scrubbed_key, scrubbed)
            scrubbed[output_key] = _scrub_payload(
                item,
                rule_set,
                account_rule_enabled=account_rule_enabled,
                redact_account_value=redact_child_account_value,
            )
        return scrubbed
    if isinstance(value, list):
        return [
            _scrub_payload(
                item,
                rule_set,
                account_rule_enabled=account_rule_enabled,
                redact_account_value=redact_account_value,
            )
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            _scrub_payload(
                item,
                rule_set,
                account_rule_enabled=account_rule_enabled,
                redact_account_value=redact_account_value,
            )
            for item in value
        )

    return value


def _is_account_context_key(key: str, scrubbed_key: Any | None = None) -> bool:
    if bool(_ACCOUNT_CONTEXT_KEY_PATTERN.match(key)):
        return True

    return (
        isinstance(scrubbed_key, str)
        and REDACTED_ACCOUNT not in key
        and REDACTED_ACCOUNT in scrubbed_key
    )


def _is_numeric_account_value(value: Any) -> bool:
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


def _unique_scrubbed_key(key: Any, scrubbed: dict[Any, Any]) -> Any:
    if key not in scrubbed:
        return key

    if not isinstance(key, str):
        return key

    collision_index = 2
    while True:
        candidate = f"{key} [DUPLICATE_KEY_{collision_index}]"
        if candidate not in scrubbed:
            return candidate
        collision_index += 1


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
