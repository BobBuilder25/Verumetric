# ADR-0003: Ticket-keyed reconciliation, a staged intake gate, and optional master data

- **Status:** Accepted
- **Date:** 2026-09-16
- **Decided by:** Tanner
- **Supersedes:** the counterpart assumption in ADR-0001 (PO-keyed matching)
- **Background:** CLAUDE.md §5 Tier 0, §6; `docs/critique/part-3.md` §1, §8

## Context

ADR-0001 assumed construction counterparts would mostly be purchase orders, and
flagged 60% counterpart coverage as the experiment's main risk. That assumption
was wrong about this vertical: contractors' paper does not reconcile through POs.
Reconciliation is the single strongest confirming evidence in the stack — it is
free, it is independent of every engine, and without it the YES-class argument
for this document population collapses to locality alone. So how counterparts
are keyed is not a detail.

## Decision

**1. Counterpart matching keys on ticket number and vendor+date, not PO number.**
The reconciliation oracles in this vertical, in descending strength:

| Oracle | Invariant | Availability |
|---|---|---|
| Supplier monthly statement ↔ individual delivery tickets | Statement lists ticket numbers and amounts; each ticket must appear once, at its amount, and the listed amounts must sum to the statement total | Common, easy to source |
| Delivery ticket ↔ supplier invoice, same ticket number | Two-way match on quantity, unit price, extended total | Common |
| Job-cost entries for a job/month | Totals per job reconcile against the tickets posted to it | From the accounting system |

The statement↔ticket oracle is the strongest of the three and was not in the
original design: it is a one-to-many match with a sum invariant, which catches
both a wrong amount *and* a missing ticket. The second is the recall check this
population otherwise lacks (part-3 §1: completeness cannot be verified locally).

PO-keyed matching stays in the schema for freight. The matcher takes a key
strategy per document class; neither key is hardcoded.

**2. Intake is staged, and counterpart coverage is measured before the rest is
sourced.** Tanner delivers 150 pages first. `tools/stratify.py` reports actual
counterpart coverage, ugly fraction, totals fraction and the ambiguity-floor
inputs on those 150 before any further sourcing.

**Gate: if measured counterpart coverage on the first 150 pages is < 50%**, we
decide then whether to lead with freight instead. Measured, not discovered after
the full run.

**3. Master-data tables are optional evidence, and unavailability is logged
distinctly from failure.** Exports (vendor list, item/parts list, open and closed
POs, price/rate history) arrive as CSV from QuickBooks or Sage. Loaders are
tolerant of messy headers and missing columns. Every document's evidence log
records **which Tier 0 checks could not run and why** — no vendor table, no rate
history, no counterpart present.

## Consequences

- A check that could not run and a check that ran and failed must never collapse
  into the same number. Without the distinction, a document that simply lacked a
  vendor table looks like a document whose vendor was wrong, and a coverage
  result driven by missing inputs would be misread as a verification result. The
  per-field log carries `UNAVAILABLE` as a first-class check outcome, and every
  coverage figure in `reports/` is reported alongside the share of fields whose
  Tier 0 evidence was unavailable.
- The statement↔ticket oracle needs a document-set abstraction, not a
  document-pair one: one statement reconciles against N tickets that arrive as
  separate pages, possibly in separate batches. The counterpart matcher is
  therefore many-to-one from the start.
- Tolerant CSV loading has a failure mode of its own: a column silently
  unmatched becomes a check that quietly never fires. Loaders report which
  columns they bound and which they did not, and that report is part of intake,
  not a debug log.
- Sourcing cost is staged, so a wrong vertical costs 150 pages of annotation
  effort rather than 500.

## Note on lineage, recorded here because it surfaced with the provider decision

The LLM-native extractor (`claude-extractor`) and the Tier 3 premium verifier
(`claude-premium-verifier`) are the same model family. For any field the Claude
extractor produced, a Tier 3 read is a **same-lineage recheck**, not independent
confirmation: the model that misread a smudged 3 as an 8 is not the obvious
choice to adjudicate whether it was a 3. Recorded in `config/lineages.yaml`:
Tier 3's likelihood ratio is held at ~1.0 for Claude-extracted fields until gold
measures the pair, and Tier 2 on those fields should prefer a different-lineage
engine. Tier 3 keeps full weight over OCR-lineage extractions, which is the case
part-3 §3 actually describes. This is why the cloud OCR adapter matters more
than its ordering suggests — until it exists, the ladder has one lineage doing
both extraction and premium adjudication for a share of fields.
