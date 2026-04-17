from __future__ import annotations

import re
from typing import Any


_NAME_PATTERN = re.compile(
    r"(?i)(\b(?:my\s+name\s+is|name(?:\s+is)?|customer\s+name|\u59d3\u540d)"
    r"\s*[:\uff1a=]?\s*)"
    r"([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2}|[\u4e00-\u9fff]{2,4})"
)
_PHONE_PATTERNS = (
    re.compile(
        r"(?<!\d)(?:\+?86[-.\s]?)?"
        r"1[3-9]\d[-.\s]?\d{4}[-.\s]?\d{4}(?!\d)"
    ),
    re.compile(
        r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}(?!\d)"
    ),
)
_ACCOUNT_PATTERN = re.compile(
    r"(?i)(\b(?:account|acct|account_id|bank\s+account|card)\b"
    r"\s*(?:number|id)?\s*[:=#-]?\s*)"
    r"((?:(?:\d[ -]?){6,}\d)|"
    r"(?:[A-Za-z0-9][A-Za-z0-9._-]{2,}[A-Za-z0-9]))"
)


def scrub_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a sanitized copy of chat messages before provider calls or replay."""
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
    scrubbed = _NAME_PATTERN.sub(r"\1[REDACTED_NAME]", value)
    for pattern in _PHONE_PATTERNS:
        scrubbed = pattern.sub("[REDACTED_PHONE]", scrubbed)
    return _ACCOUNT_PATTERN.sub(r"\1[REDACTED_ACCOUNT]", scrubbed)


__all__ = ["scrub_input"]
