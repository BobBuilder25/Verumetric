"""Tier 0: deterministic checks. Free, and run on every field.

Two populations here, and the difference decides what a PASS is worth
(CLAUDE.md §3 rule 4):

**Rejecting** - type and format, date sanity, identifier checksums, and the
sharpest of them, `value parses from source_text`. These can prove a value
wrong. None of them can make it right: a number that parses is still a number
someone may have misread.

**Confirming** - arithmetic reconciliation, cross-field consistency, master-data
match, counterpart-document match. These would have failed had the value been
wrong, which is what makes them evidence.

On the receipt corpora this file carries almost the whole confirming load:
master data and counterpart documents do not exist there, so intra-document
arithmetic is the only confirming evidence available (ADR-0005). That is why
CORD - which publishes line items, subtotal, tax and total - is the primary
corpus and FUNSD is only the recall probe.
"""

from __future__ import annotations

import ast
import operator
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from verumetric.checks.base import (
    CheckKind,
    CheckOutcome,
    CheckResult,
    not_applicable,
    unavailable,
)
from verumetric.checks.parsing import parse_date, parse_money
from verumetric.checks.weights import EvidenceWeights
from verumetric.schema import ExtractionResult, FieldClaim, FieldClass, ProvenanceType

TIER = 0


@dataclass(frozen=True)
class ClassPolicy:
    """Per-document-class conventions, from config/schemas/<class>.yaml.

    Pinning `decimal_separator` and `day_first` removes guesses the parser would
    otherwise have to make and flag. Unpinned is honest, not free: every
    ambiguous parse becomes a field carrying avoidable uncertainty.
    """

    decimal_separator: str | None = None
    day_first: bool | None = None
    money_tolerance: Decimal = Decimal("0.01")
    date_not_before: date | None = None
    date_not_after: date | None = None
    allow_negative_money: bool = True


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


# --- rejecting checks -------------------------------------------------------


def check_type_format(
    claim: FieldClaim, policy: ClassPolicy, weights: EvidenceWeights
) -> CheckResult:
    """Does the value have the shape its field class requires?"""
    cid = "tier0.type_format"
    kind = CheckKind.REJECTING

    if claim.provenance.type is ProvenanceType.ABSENT:
        return not_applicable(cid, TIER, kind, "absent claim has no value to shape-check")

    if claim.field_class is FieldClass.MONEY:
        parsed = parse_money(str(claim.value), decimal_separator=policy.decimal_separator)
        detail = {"parsed": str(parsed.value), "note": parsed.note}
        if parsed.ambiguous_separator:
            detail["ambiguous_separator"] = True
        return _result(
            cid, kind, CheckOutcome.PASS if parsed.ok else CheckOutcome.FAIL, weights, detail
        )

    if claim.field_class is FieldClass.QUANTITY:
        parsed = parse_money(str(claim.value), decimal_separator=policy.decimal_separator)
        return _result(
            cid,
            kind,
            CheckOutcome.PASS if parsed.ok else CheckOutcome.FAIL,
            weights,
            {"parsed": str(parsed.value)},
        )

    if claim.field_class is FieldClass.DATE:
        parsed = parse_date(str(claim.value), day_first=policy.day_first)
        detail = {"parsed": parsed.value.isoformat() if parsed.value else None, "note": parsed.note}
        if parsed.ambiguous_order:
            detail["ambiguous_order"] = True
        return _result(
            cid, kind, CheckOutcome.PASS if parsed.ok else CheckOutcome.FAIL, weights, detail
        )

    if claim.field_class is FieldClass.LINE_ITEM:
        ok = isinstance(claim.value, (list, dict))
        return _result(cid, kind, CheckOutcome.PASS if ok else CheckOutcome.FAIL, weights, {})

    # party / identifier / text: any non-empty string is shaped correctly.
    ok = bool(str(claim.value).strip())
    return _result(cid, kind, CheckOutcome.PASS if ok else CheckOutcome.FAIL, weights, {})


def check_value_parses_from_source_text(
    claim: FieldClaim, policy: ClassPolicy, weights: EvidenceWeights
) -> CheckResult:
    """Does the value agree with the text the provider says it read?

    The sharpest free check there is. It catches the transcription error that no
    second engine would catch, because both engines read the same pixels
    correctly and only the transcription to a number went wrong: source_text
    "$18,381.16" with value 18331.16 fails here at zero cost (part-2 §4).
    """
    cid = "tier0.value_parses_from_source_text"
    kind = CheckKind.REJECTING

    prov = claim.provenance
    if prov.type is ProvenanceType.ABSENT:
        return not_applicable(cid, TIER, kind, "absent claim has no source text")
    if prov.type in (ProvenanceType.DERIVED, ProvenanceType.INFERRED):
        return not_applicable(cid, TIER, kind, f"{prov.type} values have no single source text")
    if not prov.source_text:
        return unavailable(cid, TIER, kind, "provider supplied no source_text")

    if claim.field_class in (FieldClass.MONEY, FieldClass.QUANTITY):
        from_value = parse_money(str(claim.value), decimal_separator=policy.decimal_separator)
        from_source = parse_money(prov.source_text, decimal_separator=policy.decimal_separator)
        if not from_value.ok or not from_source.ok:
            return _result(
                cid,
                kind,
                CheckOutcome.FAIL,
                weights,
                {
                    "value": str(claim.value),
                    "source_text": prov.source_text,
                    "note": "one side did not parse as a number",
                },
            )
        agrees = from_value.value == from_source.value
        return _result(
            cid,
            kind,
            CheckOutcome.PASS if agrees else CheckOutcome.FAIL,
            weights,
            {"from_value": str(from_value.value), "from_source": str(from_source.value)},
        )

    if claim.field_class is FieldClass.DATE:
        a = parse_date(str(claim.value), day_first=policy.day_first)
        b = parse_date(prov.source_text, day_first=policy.day_first)
        if not a.ok or not b.ok:
            return _result(
                cid,
                kind,
                CheckOutcome.FAIL,
                weights,
                {"value": str(claim.value), "source_text": prov.source_text},
            )
        return _result(
            cid,
            kind,
            CheckOutcome.PASS if a.value == b.value else CheckOutcome.FAIL,
            weights,
            {"from_value": a.value.isoformat(), "from_source": b.value.isoformat()},
        )

    from verumetric.reference import similarity

    score = similarity(str(claim.value), prov.source_text)
    return _result(
        cid,
        kind,
        CheckOutcome.PASS if score >= 0.9 else CheckOutcome.FAIL,
        weights,
        {"similarity": round(score, 4)},
    )


def check_date_sanity(
    claim: FieldClaim, policy: ClassPolicy, weights: EvidenceWeights
) -> CheckResult:
    """A real calendar date, inside a plausible window for the document class."""
    cid = "tier0.date_sanity"
    kind = CheckKind.REJECTING

    if claim.field_class is not FieldClass.DATE:
        return not_applicable(cid, TIER, kind, "not a date field")
    if claim.provenance.type is ProvenanceType.ABSENT:
        return not_applicable(cid, TIER, kind, "absent claim")

    parsed = parse_date(str(claim.value), day_first=policy.day_first)
    if not parsed.ok:
        return _result(cid, kind, CheckOutcome.FAIL, weights, {"note": parsed.note})

    lo = policy.date_not_before or date(1990, 1, 1)
    hi = policy.date_not_after or (date.today() + timedelta(days=1))
    within = lo <= parsed.value <= hi
    return _result(
        cid,
        kind,
        CheckOutcome.PASS if within else CheckOutcome.FAIL,
        weights,
        {"parsed": parsed.value.isoformat(), "window": [lo.isoformat(), hi.isoformat()]},
    )


def luhn_ok(digits: str) -> bool:
    nums = [int(c) for c in digits if c.isdigit()]
    if len(nums) < 2:
        return False
    total, parity = 0, len(nums) % 2
    for i, n in enumerate(nums):
        if i % 2 == parity:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def aba_routing_ok(digits: str) -> bool:
    nums = [int(c) for c in digits if c.isdigit()]
    if len(nums) != 9:
        return False
    weights_ = (3, 7, 1, 3, 7, 1, 3, 7, 1)
    return sum(n * w for n, w in zip(nums, weights_, strict=True)) % 10 == 0


def check_identifier_checksum(
    claim: FieldClaim, policy: ClassPolicy, weights: EvidenceWeights, kind_hint: str | None = None
) -> CheckResult:
    """Checksum an identifier where its scheme has one.

    Most identifiers do not: a receipt's invoice number carries no check digit,
    so this returns NOT_APPLICABLE rather than a free pass. A check that cannot
    run must not look like a check that succeeded.
    """
    cid = "tier0.identifier_checksum"
    kind = CheckKind.REJECTING

    if claim.field_class is not FieldClass.IDENTIFIER:
        return not_applicable(cid, TIER, kind, "not an identifier field")
    if claim.provenance.type is ProvenanceType.ABSENT:
        return not_applicable(cid, TIER, kind, "absent claim")

    digits = "".join(c for c in str(claim.value) if c.isdigit())
    scheme = kind_hint
    if scheme is None:
        return not_applicable(cid, TIER, kind, "no checksum scheme declared for this identifier")

    if scheme == "aba":
        ok = aba_routing_ok(digits)
    elif scheme == "luhn":
        ok = luhn_ok(digits)
    else:
        return not_applicable(cid, TIER, kind, f"unknown checksum scheme {scheme!r}")

    return _result(
        cid, kind, CheckOutcome.PASS if ok else CheckOutcome.FAIL, weights, {"scheme": scheme}
    )


def check_money_range(
    claim: FieldClaim, policy: ClassPolicy, weights: EvidenceWeights
) -> CheckResult:
    cid = "tier0.money_range"
    kind = CheckKind.REJECTING

    if claim.field_class is not FieldClass.MONEY:
        return not_applicable(cid, TIER, kind, "not a money field")
    if claim.provenance.type is ProvenanceType.ABSENT:
        return not_applicable(cid, TIER, kind, "absent claim")

    parsed = parse_money(str(claim.value), decimal_separator=policy.decimal_separator)
    if not parsed.ok:
        return _result(cid, kind, CheckOutcome.FAIL, weights, {"note": "unparseable"})
    if parsed.value < 0 and not policy.allow_negative_money:
        return _result(cid, kind, CheckOutcome.FAIL, weights, {"value": str(parsed.value)})
    return _result(cid, kind, CheckOutcome.PASS, weights, {"value": str(parsed.value)})


# --- confirming checks ------------------------------------------------------

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def _label_values(result: ExtractionResult, policy: ClassPolicy) -> dict[str, list[Decimal]]:
    out: dict[str, list[Decimal]] = {}
    for claim in result.claims:
        if claim.provenance.type is ProvenanceType.ABSENT:
            continue
        if claim.field_class not in (FieldClass.MONEY, FieldClass.QUANTITY):
            continue
        parsed = parse_money(str(claim.value), decimal_separator=policy.decimal_separator)
        if parsed.ok:
            out.setdefault(claim.field_name, []).append(parsed.value)
    return out


def evaluate_invariant(
    expr: str, values: dict[str, list[Decimal]]
) -> tuple[bool | None, dict[str, Any]]:
    """Evaluate an arithmetic invariant from a class schema.

    A restricted AST walk - names, numbers, + - * /, sum(), and a single
    comparison - not `eval`. A schema is configuration, and configuration that
    can execute arbitrary code is a vulnerability waiting for someone to edit a
    YAML file.

    Returns (None, reason) when a referenced label is missing from the document:
    an invariant over absent fields is UNAVAILABLE, not FAIL.
    """
    missing: list[str] = []

    def resolve(name: str, aggregate: bool) -> Decimal | None:
        vals = values.get(name)
        if not vals:
            missing.append(name)
            return None
        if aggregate:
            return sum(vals, Decimal("0"))
        if len(vals) > 1:
            # Several claims for one label and no aggregation asked for: the
            # invariant is under-specified for this document. Say so.
            missing.append(f"{name} (appears {len(vals)}x, expression expects one)")
            return None
        return vals[0]

    def walk(node: ast.AST) -> Decimal | None:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant):
            return Decimal(str(node.value))
        if isinstance(node, ast.Name):
            return resolve(node.id, aggregate=False)
        if isinstance(node, ast.Attribute):
            return resolve(_dotted(node), aggregate=False)
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id != "sum" or len(node.args) != 1:
                raise ValueError("only sum(<label>) is permitted in an invariant")
            arg = node.args[0]
            return resolve(
                _dotted(arg) if isinstance(arg, ast.Attribute) else arg.id, aggregate=True
            )
        if isinstance(node, ast.BinOp):
            op = _BINOPS.get(type(node.op))
            if op is None:
                raise ValueError(
                    f"operator not permitted in an invariant: {type(node.op).__name__}"
                )
            left, right = walk(node.left), walk(node.right)
            if left is None or right is None:
                return None
            return op(left, right)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            v = walk(node.operand)
            return None if v is None else -v
        raise ValueError(f"expression element not permitted: {type(node).__name__}")

    tree = ast.parse(expr, mode="eval")
    if not isinstance(tree.body, ast.Compare) or len(tree.body.ops) != 1:
        raise ValueError("an invariant must be a single comparison")
    if not isinstance(tree.body.ops[0], ast.Eq):
        raise ValueError("only == is supported in an invariant")

    left = walk(tree.body.left)
    right = walk(tree.body.comparators[0])
    if left is None or right is None:
        return None, {"missing": missing}
    return None, {"left": left, "right": right}  # comparison happens in the caller, with tolerance


def _dotted(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def check_arithmetic_reconciliation(
    result: ExtractionResult,
    invariant: dict[str, Any],
    policy: ClassPolicy,
    weights: EvidenceWeights,
) -> CheckResult:
    """Run one invariant over a document's claims.

    This is the confirming check that carries the YES-class argument: a total
    that survives the sum of its own line items would not have survived had it
    been misread. It costs nothing and needs no second engine.
    """
    cid = f"tier0.arithmetic.{invariant.get('id', 'unnamed')}"
    kind = CheckKind.CONFIRMING
    values = _label_values(result, policy)

    try:
        _, detail = evaluate_invariant(invariant["expr"], values)
    except ValueError as exc:
        return not_applicable(cid, TIER, kind, f"invalid invariant: {exc}")

    if "missing" in detail:
        return unavailable(
            cid, TIER, kind, f"labels absent from this document: {', '.join(detail['missing'])}"
        )

    left, right = detail["left"], detail["right"]
    tolerance = Decimal(str(invariant.get("tolerance", policy.money_tolerance)))
    holds = abs(left - right) <= tolerance
    return CheckResult(
        check_id=cid,
        tier=TIER,
        kind=kind,
        outcome=CheckOutcome.PASS if holds else CheckOutcome.FAIL,
        likelihood_ratio=weights.lr(
            "tier0.arithmetic_reconciliation",
            CheckOutcome.PASS if holds else CheckOutcome.FAIL,
            kind,
        ),
        detail={
            "expr": invariant["expr"],
            "left": str(left),
            "right": str(right),
            "difference": str(left - right),
            "tolerance": str(tolerance),
        },
    )


def check_master_data_match(
    claim: FieldClaim, master_data: Any, weights: EvidenceWeights
) -> CheckResult:
    """Match a field against customer master data, when there is any.

    There is none in the public corpora (ADR-0005), so this reports UNAVAILABLE
    for every field there. That is the point: measured coverage is a lower
    bound, and this check is one of the reasons why.
    """
    cid = "tier0.master_data_match"
    if master_data is None:
        return unavailable(
            cid,
            TIER,
            CheckKind.CONFIRMING,
            "no master-data tables supplied for this document class",
        )
    raise NotImplementedError("master-data matching lands with the first customer export")


def check_counterpart_match(
    claim: FieldClaim, counterparts: Any, weights: EvidenceWeights
) -> CheckResult:
    """Match against a counterpart document (statement, PO, BOL, ticket).

    The strongest confirming evidence in the stack, and absent from every public
    corpus. Stubbed to UNAVAILABLE so a coverage shortfall is attributable
    rather than mistaken for a verification failure (ADR-0003, ADR-0005).
    """
    cid = "tier0.counterpart_match"
    if not counterparts:
        return unavailable(
            cid, TIER, CheckKind.CONFIRMING, "no counterpart documents available in this corpus"
        )
    raise NotImplementedError("counterpart matching lands with customer data")
