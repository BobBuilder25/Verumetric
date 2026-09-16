"""Tests for check results, parsing, and evidence weights.

All values SYNTHETIC. The parsing cases are the ones that actually bite on the
primary corpus (Indonesian receipts), not illustrative examples.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from verumetric.checks.base import (
    CheckKind,
    CheckOutcome,
    CheckResult,
    not_applicable,
    unavailable,
)
from verumetric.checks.parsing import parse_date, parse_money, parse_quantity
from verumetric.checks.weights import EvidenceWeights

# --- CheckResult invariants -------------------------------------------------


def test_rejecting_check_cannot_confirm_on_pass():
    """CLAUDE.md §3 rule 4, enforced in the type so no code path can drift."""
    with pytest.raises(ValueError, match="confirms nothing"):
        CheckResult("tier0.type_format", 0, CheckKind.REJECTING, CheckOutcome.PASS, 3.0)


def test_rejecting_check_may_reject_hard():
    r = CheckResult("tier0.type_format", 0, CheckKind.REJECTING, CheckOutcome.FAIL, 0.02)
    assert r.likelihood_ratio == 0.02


def test_confirming_check_may_confirm():
    r = CheckResult("tier0.arithmetic", 0, CheckKind.CONFIRMING, CheckOutcome.PASS, 15.0)
    assert r.likelihood_ratio == 15.0


def test_a_check_that_did_not_run_carries_no_evidence():
    with pytest.raises(ValueError, match="carries no evidence"):
        CheckResult("x", 0, CheckKind.CONFIRMING, CheckOutcome.UNAVAILABLE, 5.0)


def test_zero_likelihood_ratio_is_refused():
    """Absolute certainty from one check would make later evidence unable to
    move the posterior at all."""
    with pytest.raises(ValueError, match="must be positive"):
        CheckResult("x", 0, CheckKind.CONFIRMING, CheckOutcome.FAIL, 0.0)


def test_unavailable_and_not_applicable_are_distinguishable():
    """A missing vendor table and a wrong vendor must never be the same number."""
    u = unavailable("tier0.master_data_match", 0, CheckKind.CONFIRMING, "no table supplied")
    n = not_applicable("tier0.date_sanity", 0, CheckKind.REJECTING, "not a date field")
    assert u.outcome is CheckOutcome.UNAVAILABLE
    assert n.outcome is CheckOutcome.NOT_APPLICABLE
    assert not u.ran and not n.ran


# --- money parsing ----------------------------------------------------------


def test_indonesian_thousands_separator():
    """Rp 66.000 is sixty-six thousand. Reading it as 66 would be a 1000x error
    on the primary corpus."""
    p = parse_money("Rp 66.000")
    assert p.value == Decimal("66000")
    assert p.ambiguous_separator is True


def test_us_decimal_separator():
    p = parse_money("$18,381.16")
    assert p.value == Decimal("18381.16")
    assert p.ambiguous_separator is False


def test_pinning_the_separator_removes_the_guess():
    assert parse_money("66.000", decimal_separator=",").value == Decimal("66000")
    assert parse_money("66.000", decimal_separator=".").value == Decimal("66.000")
    assert parse_money("66.000", decimal_separator=",").ambiguous_separator is False


def test_ambiguity_is_flagged_not_hidden():
    """The parser reports when it had to choose, so every guessed field is
    findable later rather than silently baked into an arithmetic check."""
    assert parse_money("1.234").ambiguous_separator is True
    assert parse_money("12.50").ambiguous_separator is False


def test_parenthesised_negative():
    assert parse_money("(45.00)").value == Decimal("-45.00")


def test_leading_minus():
    assert parse_money("-45.00").value == Decimal("-45.00")


@pytest.mark.parametrize("text", ["", "   ", "abc", "N/A", "-"])
def test_unparseable_money_returns_none_with_a_reason(text):
    p = parse_money(text)
    assert p.value is None and not p.ok and p.note


def test_quantity_parses_like_money():
    assert parse_quantity("2") == Decimal("2")


# --- date parsing -----------------------------------------------------------


def test_iso_date():
    assert parse_date("2026-07-14").value == date(2026, 7, 14)


def test_day_month_ambiguity_is_flagged():
    """03/04/2026 is two different dates and no amount of staring resolves it."""
    p = parse_date("03/04/2026")
    assert p.ambiguous_order is True


def test_pinning_day_first_resolves_the_ambiguity():
    assert parse_date("03/04/2026", day_first=True).value == date(2026, 4, 3)
    assert parse_date("03/04/2026", day_first=False).value == date(2026, 3, 4)


def test_unambiguous_when_day_exceeds_twelve():
    p = parse_date("25/12/2026")
    assert p.value == date(2026, 12, 25)
    assert p.ambiguous_order is False


def test_impossible_date_does_not_parse():
    assert parse_date("2026-13-45").value is None


# --- weights ----------------------------------------------------------------


def test_weights_load_from_the_committed_config():
    w = EvidenceWeights.load()
    assert w.lr("tier0.arithmetic_reconciliation", CheckOutcome.PASS, CheckKind.CONFIRMING) > 1.0
    assert w.lr("tier0.value_parses_from_source_text", CheckOutcome.FAIL, CheckKind.REJECTING) < 0.1


def test_rejecting_pass_is_forced_to_one_even_if_config_says_otherwise():
    w = EvidenceWeights(table={"x": {"lr_confirm": 9.0, "lr_reject": 0.1}})
    assert w.lr("x", CheckOutcome.PASS, CheckKind.REJECTING) == 1.0


def test_checks_that_did_not_run_weigh_nothing():
    w = EvidenceWeights(table={})
    assert w.lr("anything", CheckOutcome.UNAVAILABLE, CheckKind.CONFIRMING) == 1.0
    assert w.lr("anything", CheckOutcome.NOT_APPLICABLE, CheckKind.CONFIRMING) == 1.0


def test_an_unconfigured_check_is_an_error_not_a_silent_one():
    """A silent 1.0 turns a check into decoration nobody notices."""
    w = EvidenceWeights(table={}, strict=True)
    with pytest.raises(KeyError, match="no likelihood ratio configured"):
        w.lr("tier0.mystery", CheckOutcome.PASS, CheckKind.CONFIRMING)


def test_every_check_in_the_config_has_both_directions():
    w = EvidenceWeights.load()
    for check_id, entry in w.table.items():
        assert entry.get("lr_confirm") is not None, f"{check_id} missing lr_confirm"
        assert entry.get("lr_reject") is not None, f"{check_id} missing lr_reject"
        if entry.get("kind") == "rejecting":
            assert entry["lr_confirm"] == 1.0, f"{check_id} is rejecting but confirms on pass"
