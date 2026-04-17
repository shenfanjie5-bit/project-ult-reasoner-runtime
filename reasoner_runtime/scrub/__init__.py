from __future__ import annotations

import re
from typing import Any


_PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
_ACCOUNT_PATTERN = re.compile(
    r"\b(?:account|acct|account_id|account number)\s*(?:is|=|:|#)?\s*"
    r"[A-Za-z0-9][A-Za-z0-9_-]{4,}\b",
    re.IGNORECASE,
)
_NAME_PATTERN = re.compile(
    r"\bname\s*(?:is|=|:)?\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\b"
)


def scrub_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_scrub_value(message) for message in messages]


def _scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return _scrub_text(value)
    if isinstance(value, list):
        return [_scrub_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _scrub_value(item) for key, item in value.items()}

    return value


def _scrub_text(value: str) -> str:
    scrubbed = _PHONE_PATTERN.sub("[REDACTED_PHONE]", value)
    scrubbed = _ACCOUNT_PATTERN.sub("[REDACTED_ACCOUNT]", scrubbed)
    return _NAME_PATTERN.sub("[REDACTED_NAME]", scrubbed)


__all__ = ["scrub_input"]
