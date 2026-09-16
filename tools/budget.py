#!/usr/bin/env python3
"""Project the full run's cost from what has actually been spent (ADR-0008).

The budget is $100 and the staged plan only works if the projection is checked
between stages rather than at the end. This reads the spend ledger and answers
one question: at the cost per page measured so far, does the rest of the run
fit in what is left?

It projects from measurement, never from the estimates in ADR-0008 - those exist
to be replaced. With no pages recorded yet it says so instead of inventing a
denominator.

Usage:
    python tools/budget.py                      # status against the default plan
    python tools/budget.py --remaining-pages 350
"""

from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path

from verumetric.costs import DEFAULT_LEDGER, SpendLedger

PLAN = {
    "1-pilot": {"pages": 50, "ceiling": Decimal("10")},
    "2-main": {"pages": 350, "ceiling": Decimal("60")},
    "reserve": {"pages": 0, "ceiling": Decimal("30")},
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    ap.add_argument("--remaining-pages", type=int, default=None)
    ap.add_argument("--limit", type=Decimal, default=None)
    args = ap.parse_args(argv)

    ledger = SpendLedger.open(args.ledger, args.limit)
    print(ledger.summary())

    pages_done = sum(r.pages for r in ledger.records)
    per_page = ledger.cost_per_page()

    print("\nplan (ADR-0008):")
    for name, stage in PLAN.items():
        pages = f"{stage['pages']} pages" if stage["pages"] else "-"
        print(f"  {name:10} {pages:12} ceiling ${stage['ceiling']}")

    if per_page is None or pages_done == 0:
        print(
            "\nNo pages recorded yet, so there is nothing to project from.\n"
            "Run stage 1 (50 pages) and this will replace ADR-0008's estimates\n"
            "with measured figures."
        )
        return 0

    remaining = args.remaining_pages
    if remaining is None:
        remaining = max(0, (PLAN["1-pilot"]["pages"] + PLAN["2-main"]["pages"]) - pages_done)

    projected = per_page * remaining
    after = ledger.total_usd + projected

    print(f"\nmeasured: ${per_page:.5f}/page over {pages_done} pages")
    print(f"projected for {remaining} more pages: ${projected:.2f}")
    print(f"total if run to completion: ${after:.2f} of ${ledger.limit_usd:.2f}")

    if after > ledger.limit_usd:
        affordable = int(ledger.remaining_usd / per_page) if per_page > 0 else 0
        print(
            f"\nDOES NOT FIT. At this rate the budget covers {affordable} more pages, "
            f"not {remaining}.\nCut the page count - not the reserve (ADR-0008)."
        )
        return 1

    headroom = ledger.limit_usd - after
    print(f"fits, with ${headroom:.2f} of headroom")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
