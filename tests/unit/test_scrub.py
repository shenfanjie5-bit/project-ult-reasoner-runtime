from __future__ import annotations

import pytest

from reasoner_runtime.scrub import scrub_input


def test_scrub_input_redacts_name_phone_and_account() -> None:
    messages = [
        {
            "role": "user",
            "content": (
                "My name is Alice Smith, phone 415-555-1234, "
                "account: ACCT-998877."
            ),
        }
    ]

    sanitized = scrub_input(messages)
    sanitized_content = sanitized[0]["content"]

    assert sanitized_content == (
        "My name is [REDACTED_NAME], phone [REDACTED_PHONE], "
        "account: [REDACTED_ACCOUNT]."
    )


def test_scrub_input_returns_sanitized_copy_without_mutating_original() -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "customer name: Bob Stone"},
                {"type": "text", "text": "call +1 (212) 555-7890"},
            ],
        }
    ]

    sanitized = scrub_input(messages)

    assert sanitized is not messages
    assert sanitized[0] is not messages[0]
    assert sanitized[0]["content"][0]["text"] == "customer name: [REDACTED_NAME]"
    assert sanitized[0]["content"][1]["text"] == "call [REDACTED_PHONE]"
    assert messages[0]["content"][0]["text"] == "customer name: Bob Stone"


@pytest.mark.parametrize(
    ("content", "expected", "raw_fragments"),
    [
        (
            "account number: 1234 5678 9012 3456.",
            "account number: [REDACTED_ACCOUNT].",
            ("1234", "5678", "9012", "3456"),
        ),
        (
            "card: 4111 1111 1111 1111",
            "card: [REDACTED_ACCOUNT]",
            ("4111", "1111"),
        ),
    ],
)
def test_scrub_input_redacts_spaced_account_numbers_as_one_token(
    content: str,
    expected: str,
    raw_fragments: tuple[str, ...],
) -> None:
    sanitized = scrub_input([{"role": "user", "content": content}])
    sanitized_content = sanitized[0]["content"]

    assert sanitized_content == expected
    for raw_fragment in raw_fragments:
        assert raw_fragment not in sanitized_content
