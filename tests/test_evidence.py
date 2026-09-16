"""Tests for posterior accumulation and the stopping rule.

SYNTHETIC check results throughout. These tests encode the behaviours the design
argues for, so a future change that breaks one is changing the argument.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from verumetric.checks.base import CheckKind, CheckOutcome, CheckResult
from verumetric.evidence import (
    DEFAULT_RETRY_THRESHOLDS,
    Decision,
    FieldVerdict,
    Posterior,
    StoppingRule,
    combine,
)
from verumetric.schema import FieldClass


def confirming(check_id: str, lr: float, outcome=CheckOutcome.PASS) -> CheckResult:
    return CheckResult(check_id, 0, CheckKind.CONFIRMING, outcome, lr)


def rejecting_fail(check_id: str, lr: float) -> CheckResult:
    return CheckResult(check_id, 0, CheckKind.REJECTING, CheckOutcome.FAIL, lr)


# --- accumulation -----------------------------------------------------------


def test_no_evidence_leaves_the_prior_alone():
    p = combine(0.90, [])
    assert p.p_correct == pytest.approx(0.90)


def test_confirming_evidence_raises_confidence():
    p = combine(0.90, [confirming("tier0.arithmetic_reconciliation", 15.0)])
    assert p.p_correct > 0.90


def test_rejecting_evidence_lowers_confidence_hard():
    p = combine(0.90, [rejecting_fail("tier0.value_parses_from_source_text", 0.01)])
    assert p.p_wrong > 0.5


def test_checks_that_did_not_run_move_nothing():
    base = combine(0.90, [])
    with_unavailable = combine(
        0.90,
        [CheckResult("x", 0, CheckKind.CONFIRMING, CheckOutcome.UNAVAILABLE, 1.0)],
    )
    assert base.p_correct == pytest.approx(with_unavailable.p_correct)


def test_a_pessimistic_prior_demands_more_evidence():
    """New provider, new document class: start pessimistic so the stack gathers
    evidence rather than assuming competence."""
    weak = combine(0.70, [confirming("tier1.source_text_grounds", 4.0)])
    strong = combine(0.95, [confirming("tier1.source_text_grounds", 4.0)])
    assert weak.p_wrong > strong.p_wrong


def test_posterior_never_reaches_certainty():
    """Absolute certainty from finite evidence would make every later check
    arithmetically incapable of moving the posterior."""
    huge = [confirming(f"c{i}", 50.0) for i in range(20)]
    p = combine(0.99, huge)
    assert p.p_correct < 1.0
    assert p.p_wrong > 0.0


def test_correlated_evidence_is_damped():
    """Two checks computed from the same grounding call are not two opinions.
    Counting them as independent understates P(wrong) - the one direction we
    cannot afford to be wrong in (ADR-0007)."""
    results = [
        confirming("tier1.source_text_grounds", 4.0),
        confirming("tier1.location_agrees", 3.0),
    ]
    groups = {"tier1.source_text_grounds": "g", "tier1.location_agrees": "g"}
    damped = combine(0.90, results, groups=groups)
    naive = combine(0.90, results)
    assert damped.p_wrong > naive.p_wrong


def test_damping_keeps_the_direction_of_the_weaker_check():
    """A damped check still moves the posterior; it just cannot pose as a second
    independent opinion."""
    one = combine(0.90, [confirming("a", 4.0)], groups={"a": "g"})
    two = combine(0.90, [confirming("a", 4.0), confirming("b", 3.0)], groups={"a": "g", "b": "g"})
    assert two.p_wrong < one.p_wrong


def test_independent_evidence_is_not_damped():
    grouped = combine(
        0.90,
        [confirming("a", 4.0), confirming("b", 4.0)],
        groups={"a": "g", "b": "g"},
    )
    independent = combine(
        0.90,
        [confirming("a", 4.0), confirming("b", 4.0)],
        groups={"a": "g1", "b": "g2"},
    )
    assert independent.p_wrong < grouped.p_wrong


def test_the_strongest_check_in_a_group_counts_in_full():
    strongest_first = combine(
        0.90, [confirming("a", 9.0), confirming("b", 2.0)], groups={"a": "g", "b": "g"}
    )
    strongest_last = combine(
        0.90, [confirming("b", 2.0), confirming("a", 9.0)], groups={"a": "g", "b": "g"}
    )
    assert strongest_first.p_wrong == pytest.approx(strongest_last.p_wrong)


# --- the stopping rule ------------------------------------------------------


#: The free ladder: everything Tier 0 and Tier 1 can establish at zero cost.
FREE_LADDER = [
    confirming("tier0.arithmetic_reconciliation", 15.0),
    confirming("tier1.source_text_grounds", 4.0),
    confirming("tier1.location_agrees", 3.0),
    confirming("tier1.reference_reads_same_value", 6.0),
]
FREE_GROUPS = {
    "tier1.source_text_grounds": "grounding",
    "tier1.location_agrees": "grounding",
}


def test_a_free_check_is_always_worth_running():
    """Cost zero means the inequality can never favour stopping, so the ladder
    exhausts its free evidence before it spends anything. That is the behaviour
    that keeps Tier 2+ usage (T3) down."""
    p = combine(0.90, [confirming("tier0.arithmetic_reconciliation", 15.0)])
    decision, _ = StoppingRule().decide(p, FieldClass.MONEY, Decimal("12.37"), Decimal("0"))
    assert decision is Decision.PENDING


def test_a_cheap_field_stops_once_the_free_evidence_is_in():
    """A small charge that reconciles and grounds is not worth a paid reread."""
    p = combine(0.90, FREE_LADDER, groups=FREE_GROUPS)
    decision, detail = StoppingRule().decide(p, FieldClass.MONEY, Decimal("12.37"), Decimal("0.02"))
    assert decision is Decision.PASS
    assert "below the price of the next useful check" in detail["reason"]


def test_tier_0_alone_does_not_certify_a_money_field():
    """Arithmetic is strong but single-sourced; the grounding evidence is what
    takes a money field over the line at a 0.90 prior."""
    p = combine(0.90, [confirming("tier0.arithmetic_reconciliation", 15.0)])
    decision, _ = StoppingRule().decide(p, FieldClass.MONEY, Decimal("12.37"), Decimal("0.02"))
    assert decision is Decision.PENDING


def test_a_large_amount_keeps_climbing_on_the_same_evidence():
    """Identical evidence, different consequence: value at risk sets depth."""
    p = combine(0.90, FREE_LADDER, groups=FREE_GROUPS)
    decision, _ = StoppingRule().decide(p, FieldClass.MONEY, Decimal("250000"), Decimal("0.02"))
    assert decision is Decision.PENDING


def test_bad_evidence_sends_a_field_back():
    p = combine(0.90, [rejecting_fail("tier0.value_parses_from_source_text", 0.01)])
    decision, _ = StoppingRule().decide(p, FieldClass.MONEY, Decimal("50"), Decimal("0.02"))
    assert decision is Decision.FAIL_RETRY


def test_money_is_held_to_a_stricter_threshold_than_free_text():
    assert DEFAULT_RETRY_THRESHOLDS[FieldClass.MONEY] < DEFAULT_RETRY_THRESHOLDS[FieldClass.TEXT]


def test_exhausted_and_well_evidenced_passes():
    """Otherwise a field with P(wrong)=1e-6 would land in the exception stream
    merely because the ladder ran out, understating coverage."""
    p = Posterior(p_correct=0.999999, p_wrong=1e-6, prior_correct=0.9, log_odds=0.0)
    decision, _ = StoppingRule().decide(p, FieldClass.MONEY, Decimal("5"), None)
    assert decision is Decision.PASS


def test_exhausted_and_poorly_evidenced_is_unverified_not_passed():
    """The honest output when nothing more can be established: say so."""
    p = Posterior(p_correct=0.99, p_wrong=0.01, prior_correct=0.9, log_odds=0.0)
    decision, detail = StoppingRule().decide(p, FieldClass.MONEY, Decimal("250000"), None)
    assert decision is Decision.UNVERIFIED
    assert "unverified, not certified" in detail["reason"]


def test_high_consequence_field_never_passes_on_thin_evidence():
    """A bank-number-class consequence forces evidence gathering regardless of
    how good the prior looked."""
    p = combine(0.95, [])
    decision, _ = StoppingRule().decide(p, FieldClass.IDENTIFIER, Decimal("150"), Decimal("0.01"))
    assert decision is not Decision.PASS


# --- verdicts ---------------------------------------------------------------


def test_verdict_reports_unavailable_checks_separately():
    """Coverage shortfalls must stay attributable to missing inputs."""
    results = (
        CheckResult(
            "tier0.counterpart_match",
            0,
            CheckKind.CONFIRMING,
            CheckOutcome.UNAVAILABLE,
            1.0,
            {"reason": "no counterpart docs"},
        ),
        confirming("tier0.arithmetic_reconciliation", 15.0),
    )
    verdict = FieldVerdict(
        claim_id="c1",
        decision=Decision.PASS,
        posterior=combine(0.9, list(results)),
        tier_reached=0,
        results=results,
    )
    assert verdict.unavailable_checks == ("tier0.counterpart_match",)
    assert verdict.certified is True
    assert "unavailable_checks" in verdict.to_json()
