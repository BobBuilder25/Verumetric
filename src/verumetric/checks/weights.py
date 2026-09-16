"""Likelihood ratios, loaded from config/evidence.yaml.

Every check's evidence weight lives in one file so the weights are visible,
versioned, and recalibrated from gold in one place at the end of the run
(CLAUDE.md §5). Nothing hard-codes a weight inline - a number buried in a check
is a number nobody will ever find to correct.

A likelihood ratio here is P(observation | value correct) / P(observation |
value wrong). Above 1.0 supports correct; below 1.0 supports wrong; 1.0 says
nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from verumetric.checks.base import CheckKind, CheckOutcome

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_PATH = REPO_ROOT / "config" / "evidence.yaml"


@dataclass(frozen=True)
class EvidenceWeights:
    table: dict[str, dict[str, Any]]
    strict: bool = True

    @classmethod
    def load(cls, path: Path = DEFAULT_PATH, strict: bool = True) -> EvidenceWeights:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(table=data.get("checks") or {}, strict=strict)

    def lr(self, check_id: str, outcome: CheckOutcome, kind: CheckKind) -> float:
        """The weight this check's result carries.

        A check that did not run carries nothing. A rejecting check that passed
        carries nothing - that is the rule the whole design rests on, enforced
        here as well as in CheckResult so neither path can drift.
        """
        if outcome in (CheckOutcome.UNAVAILABLE, CheckOutcome.NOT_APPLICABLE):
            return 1.0
        if kind is CheckKind.REJECTING and outcome is CheckOutcome.PASS:
            return 1.0

        entry = self.table.get(check_id)
        if entry is None:
            if self.strict:
                raise KeyError(
                    f"no likelihood ratio configured for {check_id!r}. Add it to "
                    "config/evidence.yaml (see ADR-0007) rather than defaulting - a "
                    "silent 1.0 turns a check into decoration."
                )
            return 1.0

        key = "lr_confirm" if outcome is CheckOutcome.PASS else "lr_reject"
        value = entry.get(key)
        if value is None:
            if self.strict:
                raise KeyError(f"{check_id!r} has no {key} in config/evidence.yaml")
            return 1.0
        return float(value)
