"""Tier 1: provenance grounding against the reference layer. Near-free.

Tier 0 asks whether a value is internally coherent. Tier 1 asks the different
and harder question: is it actually on the page, where the provider said it was?

The evidence comes from a reader we own and no provider can see (ADR-0006),
which is what makes it the one check a fabricating extractor cannot satisfy
without having read the document. Three distinct facts are reported separately,
because merging them would hide failure classes that look identical in
aggregate (part-2 §5):

    the text is on the page          -> tier1.source_text_grounds
    it is where the provider said    -> tier1.location_agrees
    we read the same thing there     -> tier1.reference_reads_same_value

A hallucinated value fails the first. A value lifted from the wrong row passes
the first and fails the second - that is the subtotal reported as the total. A
genuinely ambiguous glyph passes both and fails the third.
"""

from __future__ import annotations

from typing import Any

from verumetric.checks.base import (
    CheckKind,
    CheckOutcome,
    CheckResult,
    not_applicable,
    unavailable,
)
from verumetric.checks.parsing import parse_money
from verumetric.checks.weights import EvidenceWeights
from verumetric.reference import ReferenceLayer, ground, read_region, similarity
from verumetric.schema import FieldClaim, FieldClass, ProvenanceType

TIER = 1

GROUND_SCORE_THRESHOLD = 0.85
REFERENCE_AGREEMENT_THRESHOLD = 0.85


def _result(
    check_id: str,
    kind: CheckKind,
    outcome: CheckOutcome,
    weights: EvidenceWeights,
    detail: dict[str, Any] | None = None,
) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        tier=TIER,
        kind=kind,
        outcome=outcome,
        likelihood_ratio=weights.lr(check_id, outcome, kind),
        detail=detail or {},
    )


def _requires_location(claim: FieldClaim, check_id: str, kind: CheckKind) -> CheckResult | None:
    prov = claim.provenance
    if prov.type is ProvenanceType.ABSENT:
        return not_applicable(check_id, TIER, kind, "absent claim has no location")
    if prov.type in (ProvenanceType.DERIVED, ProvenanceType.INFERRED):
        return not_applicable(
            check_id, TIER, kind, f"{prov.type} values have no location to ground"
        )
    if prov.bbox is None or prov.source_text is None:
        return unavailable(check_id, TIER, kind, "claim carries no bbox or source_text")
    return None


def check_source_text_grounds(
    claim: FieldClaim, layer: ReferenceLayer | None, weights: EvidenceWeights
) -> CheckResult:
    """Is the provider's `source_text` anywhere on the page we read?"""
    cid = "tier1.source_text_grounds"
    kind = CheckKind.CONFIRMING

    if layer is None:
        return unavailable(cid, TIER, kind, "no reference layer for this page")
    blocked = _requires_location(claim, cid, kind)
    if blocked:
        return blocked

    result = ground(claim.provenance.source_text, layer, claim.provenance.bbox)
    outcome = CheckOutcome.PASS if result.score >= GROUND_SCORE_THRESHOLD else CheckOutcome.FAIL
    return _result(
        cid,
        kind,
        outcome,
        weights,
        {
            "score": round(result.score, 4),
            "matched_text": result.matched_text,
            "threshold": GROUND_SCORE_THRESHOLD,
        },
    )


def check_location_agrees(
    claim: FieldClaim, layer: ReferenceLayer | None, weights: EvidenceWeights
) -> CheckResult:
    """Is the text where the provider claimed it was?

    Reported separately from whether the text exists at all. A PASS here after a
    FAIL there is impossible; a FAIL here after a PASS there is the
    right-value-wrong-location class, and it is the reason these are two checks.
    """
    cid = "tier1.location_agrees"
    kind = CheckKind.CONFIRMING

    if layer is None:
        return unavailable(cid, TIER, kind, "no reference layer for this page")
    blocked = _requires_location(claim, cid, kind)
    if blocked:
        return blocked

    result = ground(claim.provenance.source_text, layer, claim.provenance.bbox)
    if not result.found or result.score < GROUND_SCORE_THRESHOLD:
        return not_applicable(cid, TIER, kind, "text did not ground; location is moot")

    outcome = CheckOutcome.PASS if result.location_agrees else CheckOutcome.FAIL
    return _result(
        cid,
        kind,
        outcome,
        weights,
        {
            "iou": round(result.iou or 0.0, 4),
            "claimed": [
                claim.provenance.bbox.x0,
                claim.provenance.bbox.y0,
                claim.provenance.bbox.x1,
                claim.provenance.bbox.y1,
            ],
            "found_at": [result.bbox.x0, result.bbox.y0, result.bbox.x1, result.bbox.y1],
        },
    )


def check_reference_reads_same_value(
    claim: FieldClaim, layer: ReferenceLayer | None, weights: EvidenceWeights, policy=None
) -> CheckResult:
    """What do we independently read in that region?

    A second reader of different lineage, for free. Weaker than a premium reread
    - the reference engine is cheap and struggles on the ugly stratum - but it
    is independent, which two hosted engines sharing a backbone are not.
    """
    cid = "tier1.reference_reads_same_value"
    kind = CheckKind.CONFIRMING

    if layer is None:
        return unavailable(cid, TIER, kind, "no reference layer for this page")
    blocked = _requires_location(claim, cid, kind)
    if blocked:
        return blocked

    ours = read_region(layer, claim.provenance.bbox)
    if not ours.strip():
        return unavailable(cid, TIER, kind, "reference layer read nothing in that region")

    if claim.field_class in (FieldClass.MONEY, FieldClass.QUANTITY):
        sep = getattr(policy, "decimal_separator", None)
        theirs = parse_money(str(claim.value), decimal_separator=sep)
        mine = parse_money(ours, decimal_separator=sep)
        if theirs.ok and mine.ok:
            agrees = theirs.value == mine.value
            return _result(
                cid,
                kind,
                CheckOutcome.PASS if agrees else CheckOutcome.FAIL,
                weights,
                {"provider": str(theirs.value), "reference": str(mine.value)},
            )

    score = similarity(str(claim.value), ours)
    outcome = CheckOutcome.PASS if score >= REFERENCE_AGREEMENT_THRESHOLD else CheckOutcome.FAIL
    return _result(
        cid, kind, outcome, weights, {"similarity": round(score, 4), "reference_read": ours}
    )


def check_multi_occurrence_agreement(
    claim: FieldClaim, siblings: list[FieldClaim], weights: EvidenceWeights, policy=None
) -> CheckResult:
    """When a value appears in several places, do those places agree?

    Free corroboration where the document repeats itself - a total in the header
    and again at the foot. Disagreement between two occurrences is a strong flag
    and never a vote: which one is right is not settled by counting.
    """
    cid = "tier1.multi_occurrence_agreement"
    kind = CheckKind.CONFIRMING

    others = [c for c in siblings if c.claim_id != claim.claim_id]
    if not others:
        return not_applicable(cid, TIER, kind, "value appears once; nothing to corroborate")

    sep = getattr(policy, "decimal_separator", None)
    if claim.field_class in (FieldClass.MONEY, FieldClass.QUANTITY):
        mine = parse_money(str(claim.value), decimal_separator=sep)
        readings = [parse_money(str(o.value), decimal_separator=sep) for o in others]
        parsed = [r.value for r in readings if r.ok]
        if not mine.ok or not parsed:
            return unavailable(cid, TIER, kind, "occurrences did not parse")
        agrees = all(v == mine.value for v in parsed)
        return _result(
            cid,
            kind,
            CheckOutcome.PASS if agrees else CheckOutcome.FAIL,
            weights,
            {"occurrences": [str(v) for v in parsed], "this": str(mine.value)},
        )

    scores = [similarity(str(claim.value), str(o.value)) for o in others]
    agrees = all(s >= REFERENCE_AGREEMENT_THRESHOLD for s in scores)
    return _result(
        cid,
        kind,
        CheckOutcome.PASS if agrees else CheckOutcome.FAIL,
        weights,
        {"similarities": [round(s, 4) for s in scores]},
    )
