"""Posterior accumulation and the stopping rule (CLAUDE.md §5).

Not a sequence of gates. Each check contributes a likelihood ratio, the
posterior updates, and after every check the same question is asked: is another
check worth its price?

    PASS        P(wrong) x consequence < cost of the cheapest remaining check
                that could change the decision
    FAIL/RETRY  P(wrong) exceeds the field class's retry threshold
    UNVERIFIED  checks exhausted, or what remains is too correlated with what has
                already been gathered to be worth its cost

That inequality is the whole economic argument in one line: a $12 charge that
reconciles stops at Tier 0, and a $250,000 total with a Tier 2 disagreement
keeps climbing. Nothing votes; nothing is decided by counting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from verumetric.checks.base import CheckOutcome, CheckResult
from verumetric.schema import FieldClass

# Guard rails on the posterior. Absolute certainty is never justified by any
# finite amount of evidence, and letting the posterior reach 0 or 1 would make
# every later check arithmetically incapable of moving it.
MIN_P = 1e-6
MAX_P = 1.0 - 1e-6


class Decision(StrEnum):
    PASS = "pass"
    FAIL_RETRY = "fail_retry"
    UNVERIFIED = "unverified"
    PENDING = "pending"


#: P(wrong) above which a field is sent back rather than certified. Money and
#: identifiers are strict because their consequence is high and their exception
#: cost is low - returning a null a human fills in is cheap; a wrong total is not.
DEFAULT_RETRY_THRESHOLDS: dict[FieldClass, float] = {
    FieldClass.MONEY: 0.02,
    FieldClass.IDENTIFIER: 0.02,
    FieldClass.QUANTITY: 0.05,
    FieldClass.DATE: 0.05,
    FieldClass.PARTY: 0.10,
    FieldClass.LINE_ITEM: 0.05,
    FieldClass.TEXT: 0.20,
}


@dataclass(frozen=True)
class Posterior:
    """Where the evidence has landed, and how it got there."""

    p_correct: float
    p_wrong: float
    prior_correct: float
    log_odds: float
    applied: tuple[tuple[str, float], ...] = ()

    @property
    def confident(self) -> bool:
        return self.p_wrong < 0.01


def combine(
    prior_correct: float,
    results: list[CheckResult],
    *,
    groups: dict[str, str] | None = None,
    damping: float = 0.3,
) -> Posterior:
    """Accumulate evidence in log-odds, damping correlated checks.

    Within a correlation group the strongest likelihood ratio counts in full and
    the rest are raised to `damping`. Multiplying correlated evidence as if it
    were independent manufactures confidence, and it does so in the one
    direction we cannot afford: it understates P(wrong), which inflates the
    certified stream and hides residual error (ADR-0007).
    """
    prior = min(max(prior_correct, MIN_P), MAX_P)
    log_odds = math.log(prior / (1 - prior))

    contributions: list[tuple[str, float, str | None]] = []
    for r in results:
        if not r.ran or r.likelihood_ratio == 1.0:
            continue
        group = (groups or {}).get(r.check_id)
        contributions.append((r.check_id, r.likelihood_ratio, group))

    # Strongest evidence per group counts fully; the rest are damped. "Strongest"
    # means furthest from 1.0 in log space, in either direction.
    strongest: dict[str, float] = {}
    for _, lr, group in contributions:
        if group is None:
            continue
        if group not in strongest or abs(math.log(lr)) > abs(math.log(strongest[group])):
            strongest[group] = lr

    applied: list[tuple[str, float]] = []
    seen_full: set[str] = set()
    for check_id, lr, group in contributions:
        if group is None:
            effective = lr
        elif group not in seen_full and lr == strongest[group]:
            effective = lr
            seen_full.add(group)
        else:
            effective = lr**damping
        log_odds += math.log(effective)
        applied.append((check_id, effective))

    p_correct = 1 / (1 + math.exp(-log_odds)) if log_odds > -700 else MIN_P
    p_correct = min(max(p_correct, MIN_P), MAX_P)
    return Posterior(
        p_correct=p_correct,
        p_wrong=1 - p_correct,
        prior_correct=prior,
        log_odds=log_odds,
        applied=tuple(applied),
    )


@dataclass(frozen=True)
class StoppingRule:
    """The inequality, with its one interpretive choice made explicit.

    CLAUDE.md §5 says UNVERIFIED when checks are exhausted. Read literally that
    would leave a field with P(wrong) = 1e-6 and a $5 consequence unverified
    merely because the ladder ran out - which would dump well-evidenced fields
    into the exception stream and understate coverage.

    So exhaustion is resolved by the same economics: if expected loss is below
    `exhausted_pass_floor_usd` - the price of the cheapest escalation we would
    have been willing to buy - the field passes; otherwise it is genuinely
    UNVERIFIED, meaning we could not establish it and are saying so.
    """

    retry_thresholds: dict[FieldClass, float] = field(
        default_factory=lambda: dict(DEFAULT_RETRY_THRESHOLDS)
    )
    exhausted_pass_floor_usd: Decimal = Decimal("0.005")

    def decide(
        self,
        posterior: Posterior,
        field_class: FieldClass,
        consequence_usd: Decimal,
        next_check_cost_usd: Decimal | None,
    ) -> tuple[Decision, dict[str, Any]]:
        threshold = self.retry_thresholds.get(field_class, 0.05)
        expected_loss = Decimal(str(posterior.p_wrong)) * consequence_usd

        detail: dict[str, Any] = {
            "p_wrong": posterior.p_wrong,
            "expected_loss_usd": str(expected_loss),
            "retry_threshold": threshold,
            "next_check_cost_usd": None
            if next_check_cost_usd is None
            else str(next_check_cost_usd),
        }

        if posterior.p_wrong >= threshold:
            detail["reason"] = "P(wrong) is above the retry threshold for this field class"
            return Decision.FAIL_RETRY, detail

        if next_check_cost_usd is None:
            if expected_loss < self.exhausted_pass_floor_usd:
                detail["reason"] = (
                    "no useful check remains and the expected loss is below the floor we "
                    "would have paid to reduce it"
                )
                return Decision.PASS, detail
            detail["reason"] = (
                "no useful check remains and the expected loss is still worth more than the "
                "evidence we can buy - the field is unverified, not certified"
            )
            return Decision.UNVERIFIED, detail

        if expected_loss < next_check_cost_usd:
            detail["reason"] = "expected loss is below the price of the next useful check"
            return Decision.PASS, detail

        detail["reason"] = "the next check is worth its price; escalate"
        return Decision.PENDING, detail


@dataclass(frozen=True)
class FieldVerdict:
    """The outcome for one field, with the whole path that produced it."""

    claim_id: str
    decision: Decision
    posterior: Posterior
    tier_reached: int
    results: tuple[CheckResult, ...]
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def certified(self) -> bool:
        return self.decision is Decision.PASS

    @property
    def unavailable_checks(self) -> tuple[str, ...]:
        """Checks that could not run - reported separately from failures, always."""
        return tuple(r.check_id for r in self.results if r.outcome is CheckOutcome.UNAVAILABLE)

    def to_json(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "decision": str(self.decision),
            "p_wrong": self.posterior.p_wrong,
            "prior_correct": self.posterior.prior_correct,
            "tier_reached": self.tier_reached,
            "unavailable_checks": list(self.unavailable_checks),
            "checks": [r.to_json() for r in self.results],
            "detail": self.detail,
        }
