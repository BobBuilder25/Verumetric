"""Value parsing. Tier 0 owns this, and nothing upstream of it does.

The claim schema stores what a provider said, verbatim (ADR-0002). Turning
"Rp 66.000" into a number is a *check* with a recorded outcome, not a silent
conversion - because the same operation is also one of the sharpest rejecting
checks available: a value that does not parse from its own `source_text` has
already failed (part-2 §4 uses "$18,381.16" -> 18331.16 as the worked example).

Separator ambiguity is handled explicitly rather than guessed at. The primary
corpus is Indonesian receipts, where "66.000" means sixty-six thousand, while
the same string on a US invoice means sixty-six. Getting this wrong by a factor
of a thousand on money fields would corrupt every arithmetic check downstream,
so the parser reports when it had to choose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

_CURRENCY_CHARS = re.compile(r"[$€£¥₩₹]|\b(?:rp|idr|usd|myr|sgd|eur|gbp)\b\.?", re.IGNORECASE)
_NOT_NUMERIC = re.compile(r"[^\d.,\-()]")


@dataclass(frozen=True)
class ParsedMoney:
    """A parsed amount, plus whether the parse required a judgement call."""

    value: Decimal | None
    ambiguous_separator: bool = False
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.value is not None


def parse_money(text: str, *, decimal_separator: str | None = None) -> ParsedMoney:
    """Parse an amount from provider text.

    `decimal_separator` pins the convention when the document class knows it
    ("," for Indonesian, "." for US). Without it the parser infers, and flags the
    inference so an auditor can find every field where it guessed:

      - Both separators present: the LAST one is the decimal separator.
      - One separator, followed by exactly 3 digits, and no other separator:
        thousands (66.000 -> 66000). Ambiguous, and flagged - this is the
        Indonesian case, and also how a US invoice writes sixty-six point zero
        zero zero, which nobody writes.
      - One separator followed by 1, 2 or 4+ digits: decimal.
    """
    if text is None:
        return ParsedMoney(None, note="no text")

    raw = str(text).strip()
    if not raw:
        return ParsedMoney(None, note="empty")

    cleaned = _CURRENCY_CHARS.sub("", raw)
    negative = "(" in cleaned and ")" in cleaned
    cleaned = _NOT_NUMERIC.sub("", cleaned).replace("(", "").replace(")", "")
    if cleaned.startswith("-"):
        negative = True
    cleaned = cleaned.lstrip("-")
    if not cleaned or not any(ch.isdigit() for ch in cleaned):
        return ParsedMoney(None, note=f"no digits in {raw!r}")

    ambiguous = False
    note = ""
    has_comma, has_dot = "," in cleaned, "." in cleaned

    if decimal_separator in (",", "."):
        dec, thou = decimal_separator, ("." if decimal_separator == "," else ",")
        cleaned = cleaned.replace(thou, "").replace(dec, ".")
        note = f"decimal separator pinned to {dec!r} by the document class"
    elif has_comma and has_dot:
        dec = "," if cleaned.rfind(",") > cleaned.rfind(".") else "."
        thou = "." if dec == "," else ","
        cleaned = cleaned.replace(thou, "").replace(dec, ".")
        note = f"both separators present; last ({dec!r}) taken as decimal"
    elif has_comma or has_dot:
        sep = "," if has_comma else "."
        tail = cleaned.rsplit(sep, 1)[1]
        if len(tail) == 3 and cleaned.count(sep) >= 1:
            cleaned = cleaned.replace(sep, "")
            ambiguous = True
            note = (
                f"{sep!r} followed by exactly 3 digits read as a thousands separator; "
                "pin the document class's decimal_separator to remove the guess"
            )
        else:
            cleaned = cleaned.replace(sep, ".")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return ParsedMoney(None, note=f"not a number after cleaning: {cleaned!r}")

    return ParsedMoney(-value if negative else value, ambiguous_separator=ambiguous, note=note)


def parse_quantity(text: str) -> Decimal | None:
    parsed = parse_money(text)
    return parsed.value


_DATE_PATTERNS = (
    ("%Y-%m-%d", re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")),
    ("%d/%m/%Y", re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")),
    ("%m/%d/%Y", re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")),
    ("%d-%m-%Y", re.compile(r"^\d{1,2}-\d{1,2}-\d{4}$")),
    ("%d.%m.%Y", re.compile(r"^\d{1,2}\.\d{1,2}\.\d{4}$")),
    ("%d %b %Y", re.compile(r"^\d{1,2} [A-Za-z]{3,} \d{4}$")),
    ("%b %d, %Y", re.compile(r"^[A-Za-z]{3,} \d{1,2}, \d{4}$")),
)


@dataclass(frozen=True)
class ParsedDate:
    value: date | None
    ambiguous_order: bool = False
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.value is not None


def parse_date(text: str, *, day_first: bool | None = None) -> ParsedDate:
    """Parse a date, flagging the day/month ambiguity rather than hiding it.

    03/04/2026 is two different dates depending on the convention, and no amount
    of staring at the string resolves it. When both readings are valid and the
    class has not pinned an order, the parse is returned with
    `ambiguous_order=True` so the field carries that uncertainty into the
    evidence stack instead of a false precision.
    """
    from datetime import datetime

    if not text or not str(text).strip():
        return ParsedDate(None, note="empty")
    raw = str(text).strip()

    candidates: list[tuple[str, date]] = []
    for fmt, pattern in _DATE_PATTERNS:
        if not pattern.match(raw):
            continue
        try:
            candidates.append((fmt, datetime.strptime(raw, fmt).date()))
        except ValueError:
            continue

    if not candidates:
        return ParsedDate(None, note=f"no known date format matches {raw!r}")

    distinct = {d for _, d in candidates}
    if len(distinct) == 1:
        return ParsedDate(candidates[0][1])

    dmy = next((d for fmt, d in candidates if fmt.startswith("%d")), None)
    mdy = next((d for fmt, d in candidates if fmt.startswith("%m")), None)
    if day_first is True and dmy:
        return ParsedDate(dmy, note="day-first pinned by the document class")
    if day_first is False and mdy:
        return ParsedDate(mdy, note="month-first pinned by the document class")

    chosen = dmy or candidates[0][1]
    return ParsedDate(
        chosen,
        ambiguous_order=True,
        note="day/month order is ambiguous and unpinned; both readings are valid dates",
    )
