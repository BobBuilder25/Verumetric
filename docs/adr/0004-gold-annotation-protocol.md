# ADR-0004: Gold annotation protocol

- **Status:** Accepted
- **Date:** 2026-09-16
- **Decided by:** Tanner
- **Implements:** CLAUDE.md §3 rule 6, §6 (Gold)

## Context

Gold is the measuring instrument. Every threshold in `THRESHOLDS.md` is computed
against it, so a contaminated gold set does not produce a wrong number — it
produces a confident wrong number, and nothing downstream can detect it. The
specific contamination risk is stated in CLAUDE.md §3 rule 6: gold built from
provider output inherits provider errors, and a residual measured against it
understates itself by exactly the amount that matters most.

## Decision

**Annotators.** One hired annotator plus Tanner. Two independent passes over the
150 pages; disagreements adjudicated together and **every disagreement logged**,
not just its resolution.

**Provider output is physically unavailable in the annotation view.** Not hidden,
not collapsed, not behind a toggle — the tool does not load it. The annotator
sees the page image and the reference-layer words, and nothing else. A view that
*could* show provider output is one keystroke from contaminating the instrument.

**Tanner annotates his 150 before any arm runs.** Annotating after seeing arm
output is contamination of the same kind, applied to the person who knows what
the numbers need to say.

**Timestamps are recorded per annotation** — when each field was annotated, by
whom, and when each arm ran. Contamination becomes auditable after the fact
rather than a matter of recollection: if an annotation timestamp falls after an
arm run, the reviewer can see it.

**Inter-annotator agreement is reported per field class.** Per part-3 §5: if
humans agree on under 97% of fields, that is the accuracy ceiling and some of
the providers' "errors" are not errors.

## Consequences

- The annotation tool is offline and local (`tools/annotate/`), reads only the
  page image and `data/reference/{doc_id}.json`, and writes to `data/gold/`. It
  has no code path that imports provider output — enforced by the tool's own
  test, not by discipline.
- Tanner is both an annotator and the person who decides GO. The timestamp log
  and the double-annotation are what keep that from being an unfalsifiable
  arrangement; a reviewer can check that gold predates the arms.
- Disagreement logs are training data for the consequence and ambiguity analysis:
  a field class where two humans disagree often is a field class where the
  ambiguity floor (T9) is real rather than a provider failure.
- Adjudicating together rather than by a third annotator is cheaper and is fine
  for two people, but it means adjudicated values are not independent of either
  annotator. Report inter-annotator agreement from the *pre-adjudication* passes;
  the post-adjudication set is gold, not evidence about annotator quality.
