# ADR-0002: Claim values are JSON-native; Decimal and date are refused

- **Status:** Accepted
- **Date:** 2026-09-16
- **Affects:** `src/verumetric/schema.py`

## Context

Everything in this phase is Python scripts plus flat files — JSONL and Parquet
(CLAUDE.md §3 rule 8). Every claim is written to a log and read back by scoring,
by the arms, and by whoever reviews the run cold.

`FieldClaim.value` has to hold whatever a provider claimed, so it is a union.
Two Python types round-trip through JSON as something else:

- `Decimal("18381.16")` serializes to the JSON string `"18381.16"` and returns
  as `str`, because a JSON string matches `str` exactly in a smart union.
- `date(2026, 7, 14)` does the same.

A round-trip test caught it. Left alone, an in-memory run and a replay from its
own log would disagree about what the provider said, and any comparison that
branched on type would be quietly wrong in one of them.

A second hazard sits next to it: `float` for money. `18381.16` has no exact
binary representation, so the amount logged is not the amount read.

## Decision

1. `ClaimValue` is `bool | int | float | str | list | dict | None`. `Decimal`
   and `date`/`datetime` are rejected with a message that says what to do
   instead: carry the provider's text and let Tier 0 parse it.
2. Money values must not be `float`. Adapters keep the provider's text — parse
   JSON with `parse_float=str` — so exactness is preserved at the boundary where
   it still exists.
3. `Decimal` remains the type of *our* money: `Consequence.usd` and
   `Consequence.multiplier`. Those fields are not unions, so they round-trip as
   `Decimal` correctly.
4. `Consequence.amount_usd()` takes the parsed numeric value as an argument
   rather than parsing `claim.value` itself.

## Consequences

- The type of a claim is now an invariant of the log, not of the process that
  happened to build it. A parametrized test asserts every value kind round-trips
  as itself.
- Parsing lives in exactly one place: Tier 0, where "value parses from
  `source_text` after normalization" is a check with a recorded outcome and a
  likelihood ratio. Had the model normalized `"$18,381.16"` on the way in, that
  check would be testing our normalizer rather than the provider's read —
  part-2 §4 uses precisely this example as the transcription error the check
  exists to catch.
- Adapters carry the burden: they must not let a JSON parser turn money into a
  float before it reaches a claim. Worth a line in each adapter's tests.
- A derived money value we compute ourselves is stored as its string form. Mild
  friction, and it keeps one rule instead of two.

## Alternatives rejected

- **A tagged encoding** (`{"__decimal__": "18381.16"}`) — preserves the type but
  makes every log unreadable by anything that did not import our decoder,
  against the requirement that a second model can review the artifacts cold.
- **Coercing numeric-looking strings to Decimal on input** — would destroy
  identifiers: `"0044"` becomes `44`, and leading zeros are exactly what an
  identifier check is looking at.
- **Changing the test to compare values rather than types** — the test was
  right. It described what the log has to guarantee.
