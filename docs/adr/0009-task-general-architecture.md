# ADR-0009: Task-general architecture, and the one place it does not yet hold

- **Status:** Accepted
- **Date:** 2026-09-16
- **Decided by:** Tanner (charter question 1)
- **Implements:** [docs/charter.md](../charter.md)

## Context

"Documents first, general underneath" is now a commitment: adding a second task
type must be configuration, not a rewrite. A commitment like that decays
silently unless someone checks it, so this ADR records an audit of where the
code actually stands, rather than an assertion that it is fine.

## Audit, 2026-09-16

Counting document-specific terms (page, bbox, OCR, document, crop) in `src/`,
and separating structural coupling in type signatures from prose in docstrings:

| Module | Mentions | Structural coupling? |
|---|---|---|
| `evidence.py` — posterior, stopping rule | 0 | **none** |
| `checks/weights.py` — likelihood ratios | 0 | **none** |
| `checks/base.py` — outcomes, kinds, results | 3 | none — all prose |
| `checks/parsing.py` — money, dates, quantities | 5 | none |
| `checks/tier0_deterministic.py` — invariants, vocabulary, recall | 16 | none — prose and message strings |
| `schema.py` — the claim model | 37 | **yes — `Provenance.page` and `.bbox`** |
| `checks/tier1_provenance.py` — grounding | 18 | by design — consumes the reference layer |
| `reference.py` — the reference OCR layer | 56 | by design — it *is* a document evidence source |

**The decision machinery is already task-general.** Evidence accumulation, the
stopping rule, the weight table, the check framework and the consequence model
carry no document assumptions at all. That is the part that would have been
expensive to generalise later, and it does not need to be.

The document-specific code is concentrated where it belongs: in the evidence
*sources*. A reference OCR layer is a document thing the way a test runner is a
code thing — the right shape is several sources feeding one general ladder, and
that is what exists.

## The one genuine coupling

`Provenance` carries `page: int` and `bbox: BoundingBox`. Those are document
locators. A transcription claim would want a time range; a code claim a file and
line range; a data-transformation claim a row key.

**Decision: do not generalise it yet.** The right shape is a `Locator` union
with `DocumentLocator(page, bbox)` as one member, and the migration is
mechanical — `Provenance.locator` replaces the two fields, validators move with
it, and the checks that read `prov.bbox` read `prov.locator.bbox` after
asserting the kind. Doing it now would churn ~220 tests and the entire check
surface in service of a second task type that does not exist, during a $100
experiment that is entirely documents.

**Trigger for doing it:** the first non-document task type. Not before, and not
later than that — the moment a second locator shape is needed, it is generalised
rather than special-cased into the existing fields. A `page` field holding a
segment index would be the failure this ADR exists to prevent.

## Consequences

- Adding a **document class** (freight, construction tickets, recipe cards) is
  configuration today: a schema with its invariants, vocabularies and counterpart
  keys. This is already true and is exercised by the CORD schema.
- Adding a **task type** (transcription, code review, data cleanup) is
  configuration plus an evidence source plus the locator migration above. Bounded
  and mapped, not open-ended.
- Anyone adding a task type before the locator work is done must do the migration
  first. Writing a time range into `page` would make the coupling permanent and
  invisible, which is worse than the coupling itself.
- This audit is repeatable: the grep in the table above is the check. If
  `evidence.py` ever grows a document term, generality has started leaking into
  the core and something has gone wrong.
