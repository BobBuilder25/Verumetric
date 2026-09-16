"""Check results: the common shape every tier reports in.

Four outcomes, and the distinction between the last two is not cosmetic
(ADR-0003):

    PASS            the check ran and its condition held
    FAIL            the check ran and its condition did not hold
    UNAVAILABLE     the check could not run - no master data, no counterpart
                    document, no reference layer for this page
    NOT_APPLICABLE  the check does not apply to this field at all

A missing vendor table and a wrong vendor must never collapse into the same
number. If they did, a coverage result driven by absent inputs would read as a
verification result, and the experiment would report a failure of the stack when
what it measured was a failure to supply it.

Two kinds, and the distinction is the spine of the design (CLAUDE.md §3 rule 4):

    REJECTING   can drive P(correct) toward zero on FAIL; contributes NOTHING on
                PASS. A value that parses as a number is not thereby correct.
    CONFIRMING  raises P(correct) on PASS. Reconciliation, counterpart match,
                master-data match, independent-lineage agreement.

A field passes only on positive evidence that would have failed had the value
been wrong. Format checks are not that evidence, however many of them pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class CheckOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


class CheckKind(StrEnum):
    REJECTING = "rejecting"
    CONFIRMING = "confirming"


@dataclass(frozen=True)
class CheckResult:
    """One check, run against one field claim.

    `likelihood_ratio` is the evidence weight for *correct* over *wrong*:
    above 1.0 supports correct, below 1.0 supports wrong, exactly 1.0 says
    nothing. It is supplied by config/evidence.yaml rather than invented here,
    so the weights are visible and recalibrated from gold in one place.

    `detail` may contain field values; evidence logs live under data/ and are
    never committed. Reports must not carry it (tools/stratify.py's rule).
    """

    check_id: str
    tier: int
    kind: CheckKind
    outcome: CheckOutcome
    likelihood_ratio: float = 1.0
    detail: dict[str, Any] = field(default_factory=dict)
    cost_usd: Decimal = Decimal("0")
    latency_ms: float = 0.0

    def __post_init__(self) -> None:
        if self.likelihood_ratio <= 0:
            raise ValueError("likelihood_ratio must be positive; use a small value, not zero")
        if self.kind is CheckKind.REJECTING and self.outcome is CheckOutcome.PASS:
            if self.likelihood_ratio != 1.0:
                raise ValueError(
                    f"{self.check_id}: a rejecting check that passes confirms nothing "
                    "(CLAUDE.md §3 rule 4) - its likelihood ratio on PASS must be 1.0"
                )
        if self.outcome in (CheckOutcome.UNAVAILABLE, CheckOutcome.NOT_APPLICABLE):
            if self.likelihood_ratio != 1.0:
                raise ValueError(
                    f"{self.check_id}: a check that did not run carries no evidence; "
                    "its likelihood ratio must be 1.0"
                )

    @property
    def ran(self) -> bool:
        return self.outcome in (CheckOutcome.PASS, CheckOutcome.FAIL)

    def to_json(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "tier": self.tier,
            "kind": str(self.kind),
            "outcome": str(self.outcome),
            "likelihood_ratio": self.likelihood_ratio,
            "detail": self.detail,
            "cost_usd": str(self.cost_usd),
            "latency_ms": self.latency_ms,
        }


def unavailable(check_id: str, tier: int, kind: CheckKind, reason: str) -> CheckResult:
    """A check that could not run, with the reason recorded.

    Used wherever an input is missing - no counterpart documents in the public
    corpora, no master-data export yet, no reference layer for a page. Coverage
    figures report the share of fields in this state, so a shortfall is
    attributable rather than mysterious.
    """
    return CheckResult(
        check_id=check_id,
        tier=tier,
        kind=kind,
        outcome=CheckOutcome.UNAVAILABLE,
        likelihood_ratio=1.0,
        detail={"reason": reason},
    )


def not_applicable(check_id: str, tier: int, kind: CheckKind, reason: str) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        tier=tier,
        kind=kind,
        outcome=CheckOutcome.NOT_APPLICABLE,
        likelihood_ratio=1.0,
        detail={"reason": reason},
    )
