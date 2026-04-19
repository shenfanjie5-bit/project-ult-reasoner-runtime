"""Regression tests consuming the shared ``audit_eval_fixtures`` package.

Per SUBPROJECT_TESTING_STANDARD.md §10 ``reasoner-runtime`` heavy-uses
``historical_replay_pack`` as the replay-bundle baseline. This module:

1. Walks every ``historical_replay_pack`` case and validates each
   ``replay_record.replay_bundle`` against the **five-field invariant**
   (sanitized_input/input_hash/raw_output/parsed_result/output_hash).
2. Confirms the ``audit_eval_fixtures`` package is actually installed.

**Hard-import on purpose** (codex review #1 of stage 2.1, reusable rule):
the regression tier must really consume the fixture corpus, no
``pytest.skip(allow_module_level=True)``. ImportError bubbles to pytest
collection so ``make regression`` / the regression CI lane fail loud.

Install path: ``pip install -e ".[dev,shared-fixtures]"``.
"""

from __future__ import annotations

# Hard import — fail collection if shared-fixtures extra is not installed.
from audit_eval_fixtures import (  # noqa: F401
    Case,
    CaseRef,
    iter_cases,
    list_packs,
    load_case,
)


class TestSharedFixturesAreReachable:
    def test_historical_replay_pack_present(self) -> None:
        assert "historical_replay_pack" in list_packs()

    def test_pack_has_at_least_one_case(self) -> None:
        cases = list(iter_cases("historical_replay_pack"))
        assert cases, "historical_replay_pack is empty"


class TestReplayBundleFiveFieldInvariant:
    """Every historical_replay_pack case must carry a replay_record with
    a replay_bundle whose five required fields are all present.

    This is the single most important reasoner-runtime regression
    invariant — drift in any case here would let downstream replay
    consumers (audit-eval, main-core T+1 retro) read a malformed bundle
    without surfacing a diff.
    """

    REPLAY_FIELD_NAMES = (
        "sanitized_input",
        "input_hash",
        "raw_output",
        "parsed_result",
        "output_hash",
    )

    def test_every_case_has_complete_five_field_bundle(self) -> None:
        for ref in iter_cases("historical_replay_pack"):
            case = load_case(ref.pack_name, ref.case_id)
            replay_record = case.input.get("replay_record", {})
            replay_bundle = replay_record.get("replay_bundle", {})

            missing = [
                fname for fname in self.REPLAY_FIELD_NAMES if fname not in replay_bundle
            ]
            assert not missing, (
                f"{ref.case_id}: replay_bundle missing required fields: {missing}"
            )

    def test_every_case_input_hash_is_sha256_hex(self) -> None:
        import re

        for ref in iter_cases("historical_replay_pack"):
            case = load_case(ref.pack_name, ref.case_id)
            replay_bundle = case.input.get("replay_record", {}).get(
                "replay_bundle", {}
            )

            input_hash = replay_bundle.get("input_hash", "")
            # Either a sha256: prefixed value or a 64-char hex string —
            # both are accepted shapes per stage 1.3 sample case.
            assert input_hash.startswith("sha256:") or re.fullmatch(
                r"[0-9a-fA-F]{64}", input_hash
            ), f"{ref.case_id}: input_hash {input_hash!r} is not sha256-shaped"


class TestReplayPathInvariantsExpected:
    """Every historical_replay_pack case must declare the expected
    replay-path invariants in context.json that reasoner-runtime
    promises (no_live_model_call, manifest_must_exist_before_read,
    five_replay_fields_present, hash equality).

    Drift in the *expected* invariant set would mean the fixture stops
    asserting the contract reasoner-runtime owns.
    """

    REQUIRED_INVARIANTS = {
        "no_live_model_call",
        "manifest_must_exist_before_read",
        "five_replay_fields_present",
        "input_hash_matches_recomputed_input",
        "output_hash_matches_recomputed_output",
    }

    def test_every_case_declares_required_invariants(self) -> None:
        for ref in iter_cases("historical_replay_pack"):
            case = load_case(ref.pack_name, ref.case_id)
            declared = set(
                case.context.get("expected_replay_path_invariants", [])
            )
            missing = self.REQUIRED_INVARIANTS - declared
            assert not missing, (
                f"{ref.case_id}: context missing replay-path invariants: {missing}"
            )
