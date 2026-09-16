"""Tests for Tier 0 and Tier 1 checks.

Every claim and reference layer here is SYNTHETIC. The scenarios are the real
failure classes the stack exists to catch, written as receipt-shaped data
because that is the primary corpus (ADR-0005).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from verumetric.checks.base import CheckKind, CheckOutcome
from verumetric.checks.tier0_deterministic import (
    ClassPolicy,
    aba_routing_ok,
    check_arithmetic_reconciliation,
    check_counterpart_match,
    check_date_sanity,
    check_identifier_checksum,
    check_master_data_match,
    check_type_format,
    check_value_parses_from_source_text,
    evaluate_invariant,
    luhn_ok,
)
from verumetric.checks.tier1_provenance import (
    check_location_agrees,
    check_multi_occurrence_agreement,
    check_reference_reads_same_value,
    check_source_text_grounds,
)
from verumetric.checks.weights import EvidenceWeights
from verumetric.reference import ReferenceLayer, ReferenceWord
from verumetric.schema import (
    BoundingBox,
    ExtractionResult,
    FieldClaim,
    FieldClass,
    Provenance,
)

WEIGHTS = EvidenceWeights.load()
IDN = ClassPolicy(decimal_separator=",")  # Indonesian receipts: "." is thousands


def box(x0, y0, x1, y1):
    return BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1)


def claim(
    value, *, field_class=FieldClass.MONEY, source_text=None, name="total", cid="c1", bbox=None
):
    prov = Provenance.located(
        page=1,
        bbox=bbox or box(0.70, 0.700, 0.85, 0.720),
        source_text=source_text if source_text is not None else str(value),
    )
    return FieldClaim(
        claim_id=cid, field_name=name, field_class=field_class, value=value, provenance=prov
    )


@pytest.fixture
def layer():
    """SYNTHETIC receipt page."""
    return ReferenceLayer(
        doc_id="synthetic",
        page=1,
        width=1000,
        height=1400,
        engine="synthetic",
        words=(
            ReferenceWord("NASI", box(0.10, 0.300, 0.20, 0.320)),
            ReferenceWord("GORENG", box(0.21, 0.300, 0.34, 0.320)),
            ReferenceWord("30.000", box(0.70, 0.300, 0.85, 0.320)),
            ReferenceWord("SUBTOTAL", box(0.10, 0.500, 0.28, 0.520)),
            ReferenceWord("60.000", box(0.70, 0.500, 0.85, 0.520)),
            ReferenceWord("TOTAL", box(0.10, 0.700, 0.22, 0.720)),
            ReferenceWord("66.000", box(0.70, 0.700, 0.85, 0.720)),
        ),
    )


# --- Tier 0 rejecting -------------------------------------------------------


def test_money_that_parses_passes_shape():
    r = check_type_format(claim("66.000"), IDN, WEIGHTS)
    assert r.outcome is CheckOutcome.PASS
    assert r.likelihood_ratio == 1.0, "a rejecting check that passes confirms nothing"


def test_money_that_does_not_parse_fails_shape():
    r = check_type_format(claim("N/A"), IDN, WEIGHTS)
    assert r.outcome is CheckOutcome.FAIL
    assert r.likelihood_ratio < 1.0


def test_the_transcription_error_is_caught_for_free():
    """part-2 §4's worked example: source text and value disagree, and no second
    engine would catch it because both read the pixels correctly."""
    c = claim("18331.16", source_text="$18,381.16")
    r = check_value_parses_from_source_text(c, ClassPolicy(decimal_separator="."), WEIGHTS)
    assert r.outcome is CheckOutcome.FAIL
    assert r.likelihood_ratio <= 0.01


def test_matching_source_text_passes_but_confirms_nothing():
    c = claim("18381.16", source_text="$18,381.16")
    r = check_value_parses_from_source_text(c, ClassPolicy(decimal_separator="."), WEIGHTS)
    assert r.outcome is CheckOutcome.PASS
    assert r.likelihood_ratio == 1.0


def test_derived_values_have_no_source_text_to_check():
    c = FieldClaim(
        claim_id="d1",
        field_name="total",
        field_class=FieldClass.MONEY,
        value="66000",
        provenance=Provenance.derived(derivation="subtotal + tax"),
    )
    r = check_value_parses_from_source_text(c, IDN, WEIGHTS)
    assert r.outcome is CheckOutcome.NOT_APPLICABLE


def test_missing_source_text_is_unavailable_not_failed():
    c = FieldClaim(
        claim_id="i1",
        field_name="currency",
        field_class=FieldClass.TEXT,
        value="IDR",
        provenance=Provenance.inferred(basis="letterhead"),
    )
    r = check_value_parses_from_source_text(c, IDN, WEIGHTS)
    assert r.outcome is CheckOutcome.NOT_APPLICABLE


def test_date_outside_the_window_fails():
    c = claim("1974-01-01", field_class=FieldClass.DATE, name="ticket_date")
    r = check_date_sanity(c, ClassPolicy(), WEIGHTS)
    assert r.outcome is CheckOutcome.FAIL


def test_date_inside_the_window_passes():
    c = claim("2026-07-14", field_class=FieldClass.DATE, name="ticket_date")
    assert check_date_sanity(c, ClassPolicy(), WEIGHTS).outcome is CheckOutcome.PASS


def test_checksum_schemes():
    assert aba_routing_ok("021000021") is True
    assert aba_routing_ok("021000022") is False
    assert luhn_ok("4111111111111111") is True
    assert luhn_ok("4111111111111112") is False


def test_identifier_without_a_declared_scheme_is_not_applicable():
    """A receipt's invoice number has no check digit. A check that cannot run
    must not look like one that succeeded."""
    c = claim("INV-4471", field_class=FieldClass.IDENTIFIER, name="invoice_no")
    r = check_identifier_checksum(c, IDN, WEIGHTS)
    assert r.outcome is CheckOutcome.NOT_APPLICABLE


def test_identifier_with_a_scheme_is_checked():
    c = claim("021000021", field_class=FieldClass.IDENTIFIER, name="routing")
    assert check_identifier_checksum(c, IDN, WEIGHTS, kind_hint="aba").outcome is CheckOutcome.PASS
    bad = claim("021000022", field_class=FieldClass.IDENTIFIER, name="routing")
    assert (
        check_identifier_checksum(bad, IDN, WEIGHTS, kind_hint="aba").outcome is CheckOutcome.FAIL
    )


# --- Tier 0 confirming: arithmetic ------------------------------------------


def _doc(*claims) -> ExtractionResult:
    return ExtractionResult(
        document_id="synthetic",
        document_class="cord_receipt",
        provider_id="synthetic",
        schema_version="0.1.0",
        claims=tuple(claims),
    )


def test_reconciliation_confirms_a_consistent_total():
    doc = _doc(
        claim("60.000", name="subtotal", cid="a"),
        claim("6.000", name="tax", cid="b"),
        claim("66.000", name="total", cid="c"),
    )
    inv = {"id": "sum", "expr": "subtotal + tax == total", "tolerance": "1"}
    r = check_arithmetic_reconciliation(doc, inv, IDN, WEIGHTS)
    assert r.outcome is CheckOutcome.PASS
    assert r.likelihood_ratio > 10, "passing arithmetic is the strong confirming evidence"


def test_reconciliation_catches_a_misread_total():
    doc = _doc(
        claim("60.000", name="subtotal", cid="a"),
        claim("6.000", name="tax", cid="b"),
        claim("68.000", name="total", cid="c"),
    )
    inv = {"id": "sum", "expr": "subtotal + tax == total", "tolerance": "1"}
    r = check_arithmetic_reconciliation(doc, inv, IDN, WEIGHTS)
    assert r.outcome is CheckOutcome.FAIL


def test_a_failing_invariant_is_weak_about_any_one_field():
    """It implicates a set and does not say which member is wrong, so it must not
    convict whichever field the loop happened to be looking at."""
    doc = _doc(
        claim("60.000", name="subtotal", cid="a"),
        claim("6.000", name="tax", cid="b"),
        claim("68.000", name="total", cid="c"),
    )
    inv = {"id": "sum", "expr": "subtotal + tax == total", "tolerance": "1"}
    r = check_arithmetic_reconciliation(doc, inv, IDN, WEIGHTS)
    assert 0.2 <= r.likelihood_ratio < 1.0


def test_sum_over_repeated_line_items():
    doc = _doc(
        claim("30.000", name="menu.price", cid="a"),
        claim("30.000", name="menu.price", cid="b"),
        claim("60.000", name="subtotal", cid="c"),
    )
    inv = {"id": "lines", "expr": "sum(menu.price) == subtotal", "tolerance": "1"}
    assert check_arithmetic_reconciliation(doc, inv, IDN, WEIGHTS).outcome is CheckOutcome.PASS


def test_invariant_over_absent_labels_is_unavailable_not_failed():
    """FUNSD's forms have no totals. That is a missing input, not a wrong value."""
    doc = _doc(claim("60.000", name="subtotal", cid="a"))
    inv = {"id": "sum", "expr": "subtotal + tax == total"}
    r = check_arithmetic_reconciliation(doc, inv, IDN, WEIGHTS)
    assert r.outcome is CheckOutcome.UNAVAILABLE
    assert "tax" in r.detail["reason"]


def test_tolerance_absorbs_rounding():
    doc = _doc(
        claim("60.005", name="subtotal", cid="a"),
        claim("6.000", name="tax", cid="b"),
        claim("66.00", name="total", cid="c"),
    )
    inv = {"id": "sum", "expr": "subtotal + tax == total", "tolerance": "0.01"}
    r = check_arithmetic_reconciliation(doc, inv, ClassPolicy(decimal_separator="."), WEIGHTS)
    assert r.outcome is CheckOutcome.PASS


def test_invariant_evaluator_refuses_arbitrary_code():
    """A schema is configuration, and configuration that can execute code is a
    vulnerability waiting for someone to edit a YAML file."""
    with pytest.raises(ValueError):
        evaluate_invariant("__import__('os').system('id') == 1", {})
    with pytest.raises(ValueError):
        evaluate_invariant("total > subtotal", {"total": [Decimal(1)], "subtotal": [Decimal(0)]})


# --- Tier 0: absent external evidence ---------------------------------------


def test_master_data_is_unavailable_without_tables():
    r = check_master_data_match(claim("x"), None, WEIGHTS)
    assert r.outcome is CheckOutcome.UNAVAILABLE
    assert r.likelihood_ratio == 1.0


def test_counterpart_match_is_unavailable_on_public_corpora():
    """The strongest evidence in the stack, absent here - which is exactly why
    measured coverage from this run is a lower bound (ADR-0005)."""
    r = check_counterpart_match(claim("x"), None, WEIGHTS)
    assert r.outcome is CheckOutcome.UNAVAILABLE


# --- Tier 1 -----------------------------------------------------------------


def test_a_real_value_grounds(layer):
    r = check_source_text_grounds(claim("66.000", source_text="66.000"), layer, WEIGHTS)
    assert r.outcome is CheckOutcome.PASS
    assert r.likelihood_ratio > 1.0


def test_a_hallucinated_value_does_not_ground(layer):
    """The check a fabricating extractor cannot pass: it must invent text that
    appears on a page it never read."""
    r = check_source_text_grounds(claim("99.999", source_text="99.999"), layer, WEIGHTS)
    assert r.outcome is CheckOutcome.FAIL
    assert r.likelihood_ratio < 1.0


def test_right_value_wrong_location_is_caught_by_the_second_check(layer):
    """The subtotal reported as the total: the text exists, but not where the
    provider said. Merging the two checks would hide this entirely."""
    c = claim("60.000", source_text="60.000", bbox=box(0.70, 0.700, 0.85, 0.720))
    assert check_source_text_grounds(c, layer, WEIGHTS).outcome is CheckOutcome.PASS
    assert check_location_agrees(c, layer, WEIGHTS).outcome is CheckOutcome.FAIL


def test_location_agrees_when_the_claim_is_honest(layer):
    c = claim("66.000", source_text="66.000", bbox=box(0.70, 0.700, 0.85, 0.720))
    assert check_location_agrees(c, layer, WEIGHTS).outcome is CheckOutcome.PASS


def test_reference_layer_reads_the_same_value(layer):
    c = claim("66000", source_text="66.000", bbox=box(0.68, 0.690, 0.90, 0.730))
    r = check_reference_reads_same_value(c, layer, WEIGHTS, IDN)
    assert r.outcome is CheckOutcome.PASS


def test_reference_layer_disagreement_is_evidence_not_a_verdict(layer):
    c = claim("68000", source_text="68.000", bbox=box(0.68, 0.690, 0.90, 0.730))
    r = check_reference_reads_same_value(c, layer, WEIGHTS, IDN)
    assert r.outcome is CheckOutcome.FAIL
    assert r.likelihood_ratio > 0.0, "disagreement raises risk; it does not decide"


def test_no_reference_layer_is_unavailable(layer):
    r = check_source_text_grounds(claim("66.000"), None, WEIGHTS)
    assert r.outcome is CheckOutcome.UNAVAILABLE


def test_multi_occurrence_agreement_confirms():
    a = claim("66.000", cid="a")
    b = claim("66.000", cid="b")
    r = check_multi_occurrence_agreement(a, [a, b], WEIGHTS, IDN)
    assert r.outcome is CheckOutcome.PASS


def test_multi_occurrence_disagreement_flags():
    a = claim("66.000", cid="a")
    b = claim("68.000", cid="b")
    r = check_multi_occurrence_agreement(a, [a, b], WEIGHTS, IDN)
    assert r.outcome is CheckOutcome.FAIL


def test_single_occurrence_is_not_applicable():
    a = claim("66.000", cid="a")
    r = check_multi_occurrence_agreement(a, [a], WEIGHTS, IDN)
    assert r.outcome is CheckOutcome.NOT_APPLICABLE


# --- currency (regression: found by tools/demo.py on the first run) ----------


def test_policy_converts_face_value_to_dollars():
    """Consequence is in USD; a receipt's face value is not. Feeding 66,000 IDR
    in as 66,000 USD makes a $4 field look like a $66,000 one."""
    idr = ClassPolicy(currency="IDR", usd_per_currency_unit=Decimal("0.000061"))
    assert idr.to_usd(Decimal("66000")) == pytest.approx(Decimal("4.026"))


def test_usd_documents_convert_to_themselves():
    assert ClassPolicy().to_usd(Decimal("18381.16")) == Decimal("18381.16")


def test_the_unconverted_consequence_bug_would_have_escalated_everything():
    """Documents the failure mode so it cannot come back quietly: an unconverted
    IDR consequence inflates expected loss by ~16,000x, sending every field to
    the premium tier. That fails T3 and T5 for a reason with nothing to do with
    verification - the experiment would report the wrong answer."""
    from verumetric.checks.base import CheckResult
    from verumetric.evidence import Decision, StoppingRule, combine

    evidence = [
        CheckResult(
            "tier0.arithmetic_reconciliation", 0, CheckKind.CONFIRMING, CheckOutcome.PASS, 15.0
        ),
        CheckResult("tier1.source_text_grounds", 1, CheckKind.CONFIRMING, CheckOutcome.PASS, 4.0),
        CheckResult(
            "tier1.reference_reads_same_value", 1, CheckKind.CONFIRMING, CheckOutcome.PASS, 6.0
        ),
    ]
    posterior = combine(0.90, evidence)
    rule = StoppingRule()
    idr = ClassPolicy(currency="IDR", usd_per_currency_unit=Decimal("0.000061"))
    tier2_price = Decimal("0.0013")

    converted, _ = rule.decide(
        posterior, FieldClass.MONEY, idr.to_usd(Decimal("66000")), tier2_price
    )
    unconverted, _ = rule.decide(posterior, FieldClass.MONEY, Decimal("66000"), tier2_price)

    assert converted is Decision.PASS
    assert unconverted is Decision.PENDING


# --- vocabulary and recall: the general checks for tasks without arithmetic ---

COOKING_UNITS = {"cup", "teaspoon", "tablespoon", "dash", "pinch", "ounce", "pound", "quart"}


def test_a_known_unit_confirms():
    """Closed-set membership is confirming for the same reason arithmetic is:
    most wrong readings land outside the set."""
    from verumetric.checks.tier0_deterministic import check_vocabulary_match

    c = claim("tablespoon", field_class=FieldClass.TEXT, name="unit")
    r = check_vocabulary_match(c, COOKING_UNITS, WEIGHTS, vocabulary_name="cooking_units")
    assert r.outcome is CheckOutcome.PASS
    assert r.likelihood_ratio > 1.0


def test_a_misread_unit_fails_the_vocabulary():
    from verumetric.checks.tier0_deterministic import check_vocabulary_match

    c = claim("tablespocn", field_class=FieldClass.TEXT, name="unit")
    r = check_vocabulary_match(c, COOKING_UNITS, WEIGHTS, vocabulary_name="cooking_units")
    assert r.outcome is CheckOutcome.FAIL


def test_vocabulary_matching_ignores_cosmetic_differences():
    from verumetric.checks.tier0_deterministic import check_vocabulary_match

    c = claim("TABLESPOON", field_class=FieldClass.TEXT, name="unit")
    assert check_vocabulary_match(c, COOKING_UNITS, WEIGHTS).outcome is CheckOutcome.PASS


def test_vocabulary_size_is_recorded_so_strength_can_be_recalibrated():
    """Seven units is strong evidence; a hundred thousand ingredient names is
    weak. The check must not pretend those are the same."""
    from verumetric.checks.tier0_deterministic import check_vocabulary_match

    c = claim("cup", field_class=FieldClass.TEXT, name="unit")
    r = check_vocabulary_match(c, COOKING_UNITS, WEIGHTS)
    assert r.detail["vocabulary_size"] == len(COOKING_UNITS)


def test_no_vocabulary_is_unavailable_not_failed():
    from verumetric.checks.tier0_deterministic import check_vocabulary_match

    c = claim("cup", field_class=FieldClass.TEXT, name="unit")
    assert check_vocabulary_match(c, None, WEIGHTS).outcome is CheckOutcome.UNAVAILABLE


def test_structural_recall_confirms_a_complete_list(layer):
    """The completeness check: our own OCR counts the lines without extracting
    them, which is what breaks the symmetry in 'did it miss anything'."""
    from verumetric.checks.tier0_deterministic import check_structural_recall

    r = check_structural_recall(len(layer.lines()), layer, None, WEIGHTS)
    assert r.outcome is CheckOutcome.PASS


def test_structural_recall_catches_a_dropped_item(layer):
    from verumetric.checks.tier0_deterministic import check_structural_recall

    r = check_structural_recall(len(layer.lines()) - 2, layer, None, WEIGHTS)
    assert r.outcome is CheckOutcome.FAIL
    assert r.detail["shortfall"] == 2


def test_structural_recall_tolerance_is_explicit(layer):
    """Approximate by nature - a wrapped line reads as two - so the slack is a
    stated parameter rather than a hidden fudge."""
    from verumetric.checks.tier0_deterministic import check_structural_recall

    r = check_structural_recall(len(layer.lines()) - 1, layer, None, WEIGHTS, tolerance=1)
    assert r.outcome is CheckOutcome.PASS


def test_structural_recall_without_a_reference_layer_is_unavailable():
    from verumetric.checks.tier0_deterministic import check_structural_recall

    assert check_structural_recall(5, None, None, WEIGHTS).outcome is CheckOutcome.UNAVAILABLE


def test_a_task_with_no_arithmetic_can_still_accumulate_confirming_evidence(layer):
    """The point of both checks: grandma's recipes have no sums, but vocabulary
    membership, structural recall and grounding are each confirming evidence, so
    the ladder is not empty on a document without arithmetic.

    The progression is the interesting part - it shows exactly how much evidence
    a low-consequence field needs before the economics say stop.
    """
    from verumetric.checks.tier0_deterministic import (
        check_structural_recall,
        check_vocabulary_match,
    )
    from verumetric.checks.tier1_provenance import check_source_text_grounds
    from verumetric.evidence import Decision, StoppingRule, combine

    c = claim("tablespoon", field_class=FieldClass.TEXT, name="unit", source_text="TOTAL")
    vocab = check_vocabulary_match(c, COOKING_UNITS, WEIGHTS, vocabulary_name="cooking_units")
    recall = check_structural_recall(len(layer.lines()), layer, None, WEIGHTS)
    grounds = check_source_text_grounds(c, layer, WEIGHTS)
    assert grounds.outcome is CheckOutcome.PASS

    rule = StoppingRule()
    consequence = Decimal("1.00")  # a wrong ingredient costs a bad dinner, not an invoice
    tier2 = Decimal("0.0013")

    def decide(results):
        return rule.decide(combine(0.90, results), FieldClass.TEXT, consequence, tier2)[0]

    assert decide([vocab]) is Decision.PENDING
    assert decide([vocab, recall]) is Decision.PENDING
    assert decide([vocab, recall, grounds]) is Decision.PASS


def test_the_same_evidence_escalates_when_the_stakes_are_higher(layer):
    """One system, two tasks. Identical checks on a recipe ingredient certify;
    on a field worth thousands they keep climbing. The task does not change the
    machinery - the consequence changes how much evidence it buys."""
    from verumetric.checks.tier0_deterministic import (
        check_structural_recall,
        check_vocabulary_match,
    )
    from verumetric.checks.tier1_provenance import check_source_text_grounds
    from verumetric.evidence import Decision, StoppingRule, combine

    c = claim("tablespoon", field_class=FieldClass.TEXT, name="unit", source_text="TOTAL")
    results = [
        check_vocabulary_match(c, COOKING_UNITS, WEIGHTS),
        check_structural_recall(len(layer.lines()), layer, None, WEIGHTS),
        check_source_text_grounds(c, layer, WEIGHTS),
    ]
    posterior = combine(0.90, results)
    rule = StoppingRule()

    recipe, _ = rule.decide(posterior, FieldClass.TEXT, Decimal("1.00"), Decimal("0.0013"))
    invoice, _ = rule.decide(posterior, FieldClass.TEXT, Decimal("5000"), Decimal("0.0013"))
    assert recipe is Decision.PASS
    assert invoice is Decision.PENDING
