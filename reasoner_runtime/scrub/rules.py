from __future__ import annotations

import re

from reasoner_runtime.config.models import ScrubRuleSet


REDACTED_NAME = "[REDACTED_NAME]"
REDACTED_PHONE = "[REDACTED_PHONE]"
REDACTED_ACCOUNT = "[REDACTED_ACCOUNT]"

_RULE_ORDER = ("name", "phone", "account")

_NEXT_FIELD_BOUNDARY = (
    r"(?=\s*(?:"
    r"姓名|客户|联系人|手机|电话|账户|账号|"
    r"(?i:name|customer|contact|phone|tel|telephone|account|acct|card)\b"
    r"|[,，;；。.\n\r]|$))"
)

_NAME_PATTERNS = (
    re.compile(
        r"(?P<prefix>(?:姓名|客户|联系人)\s*(?:为|是|:|：|=)?\s*)"
        r"(?P<value>[\u4e00-\u9fff]{2,4}?|[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}?)"
        + _NEXT_FIELD_BOUNDARY
    ),
    re.compile(
        r"(?P<prefix>\b(?i:name|customer|contact)\b\s*"
        r"(?:(?i:is)|=|:|#)?\s*)"
        r"(?P<value>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}?|[\u4e00-\u9fff]{2,4}?)"
        + _NEXT_FIELD_BOUNDARY,
    ),
)

_PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?86[\s-]*)?1[3-9]\d(?:[\s-]*\d){8}(?!\d)"
    r"|(?<!\d)(?:\+?1[\s.-]*)?(?:\(?\d{3}\)?[\s.-]*)\d{3}[\s.-]*\d{4}(?!\d)"
)

_ACCOUNT_PATTERN = re.compile(
    r"(?P<prefix>(?:账户|账号|account|acct|card)\s*"
    r"(?:number|no\.?)?\s*(?:为|是|is|=|:|：|#)?\s*)"
    r"(?P<value>(?:\d[\s-]*){11,18}\d)",
    re.IGNORECASE,
)


def enabled_rule_types(rule_set: ScrubRuleSet | None = None) -> set[str]:
    if rule_set is None:
        return set(_RULE_ORDER)
    if not rule_set.enabled:
        return set()

    return {rule.pattern_type for rule in rule_set.rules if rule.enabled}


def scrub_text(value: str, rule_set: ScrubRuleSet | None = None) -> str:
    enabled_rules = enabled_rule_types(rule_set)
    scrubbed = value

    if "name" in enabled_rules:
        scrubbed = _scrub_name(scrubbed)
    if "phone" in enabled_rules:
        scrubbed = _PHONE_PATTERN.sub(REDACTED_PHONE, scrubbed)
    if "account" in enabled_rules:
        scrubbed = _ACCOUNT_PATTERN.sub(
            rf"\g<prefix>{REDACTED_ACCOUNT}",
            scrubbed,
        )

    return scrubbed


def _scrub_name(value: str) -> str:
    scrubbed = value
    for pattern in _NAME_PATTERNS:
        scrubbed = pattern.sub(rf"\g<prefix>{REDACTED_NAME}", scrubbed)
    return scrubbed


__all__ = [
    "REDACTED_ACCOUNT",
    "REDACTED_NAME",
    "REDACTED_PHONE",
    "enabled_rule_types",
    "scrub_text",
]
