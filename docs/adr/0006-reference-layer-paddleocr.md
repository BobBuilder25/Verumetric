# ADR-0006: PaddleOCR as the reference layer, reference-only, with a Tesseract fallback

- **Status:** Accepted
- **Date:** 2026-09-16
- **Decided by:** Tanner
- **Implements:** CLAUDE.md §4 (reference layer), §5 Tier 1, §9 step 4

## Context

The reference layer is one cheap word-box OCR pass per page that **we own**. It
does three jobs, and its independence is what makes all three worth anything:

1. **Grounding.** Every provider's `source_text` is matched against the
   reference layer's words at the claimed location. This is the one check a
   provider cannot satisfy without actually reading the document — an extractor
   that invents a plausible value must also invent a plausible location and
   source text, and the grounding check fails it (part-2 §5, part-3 §8 item 7).
2. **Universal provenance.** Providers that emit no boxes — LLM-native
   extractors generally do not — get locations assigned by grounding against
   this layer. Without it, provenance would only exist for the OCR-native
   engines, and the provenance-first design would be optional in practice.
3. **Structure.** Line and row detection for the recall problem: when
   reconciliation fails because a line item is missing, the reference layer says
   which region was skipped (part-3 §3, Tier 4 recall repair).

The layer must therefore be free at the margin (it runs on every page, twice,
under the contamination design), independent of every hosted engine, and under
our control so no vendor change silently moves it.

## Decision

**PaddleOCR, run locally, as the reference layer.** Word-level boxes, no
endpoint, no per-page cost, no vendor account, and the model weights are ours
once fetched.

**Tesseract (TSV output) as the fallback**, if the PaddleOCR install proves
troublesome. TSV gives word-level boxes with confidences, which is the whole
requirement. It is weaker on photographed and rotated pages — precisely our
"ugly" stratum — so it is a fallback, not a peer.

**The reference layer is never an extraction arm.** It does not compete in the
six arms, its output is never a field claim, and it is never routed to. The
moment it extracts, the grounding check stops being independent of the thing it
grounds: a provider's claim would be checked against a reader that is itself
under evaluation, and a shared error would read as agreement.

**The engine is pluggable behind one interface.** `reference.py` defines the
protocol and the grounding logic; engines are thin adapters. Grounding — the
part that carries the evidence weight — is pure, deterministic, and tested
without any OCR engine installed.

## Consequences

- **Neither engine is installed in this environment yet.** PaddleOCR pulls a
  large deep-learning runtime; Tesseract needs a system package. The grounding
  logic is therefore written and tested against synthetic reference layers, and
  the engines are wired when the corpora are actually fetched. This is
  deliberate: the part that decides whether a field passes is the part that gets
  tested first, and it does not need an OCR engine to be correct.
- PaddleOCR's quality on ugly pages caps the grounding evidence available on
  exactly the stratum we deliberately over-sampled. If reference-layer recall is
  poor on blurry photographs, Tier 1 evidence weakens where it is needed most —
  a measurable effect, reported per quality stratum rather than averaged away.
- A reference layer under our control means an epoch of its own: a PaddleOCR
  version change moves every grounding score. The version is recorded in each
  page's reference JSON, so a change is visible rather than mysterious.
- Running it locally means the contamination design costs nothing extra on this
  layer — both the as-is and augmented passes are free.
- The layer sees every customer document. It is local, which is the strongest
  possible answer to a customer asking where their paper goes.

## Alternatives rejected

- **A cloud OCR as the reference layer** — per-page cost on every page twice, a
  vendor that can change under us, and it would share lineage with the cloud OCR
  extractor we intend to add, which is exactly the correlation the grounding
  check must not have.
- **An LLM as the reference layer** — the most expensive option for the highest
  volume step, non-deterministic, and same-lineage with the LLM-native
  extractor.
- **No reference layer; trust provider-supplied boxes** — provenance would exist
  only where providers volunteer it, hallucinated values would arrive with
  self-reported locations, and nothing independent would contradict them.
