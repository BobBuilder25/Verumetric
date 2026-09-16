# Pre-registered thresholds

**Status:** Pre-registration. Fixed before data. Not renegotiated.
**Date:** 2026-09-16
**Transcribed from:** `docs/critique/part-3.md` §5, §6 and §9.

> **Transcription note.** This session did not receive the canonical `CLAUDE.md`
> §7, so these thresholds are transcribed from part-3.md, which is where T1–T11,
> the kill signals and the rule-of-three note originate. Diff this file against
> §7 when the canonical brief is available. Any discrepancy is resolved in favor
> of §7 **only if no data exists yet for the affected test.**

part-3 §6 closes with: *"Thresholds fixed before data; recorded in the repo; not
renegotiated."* This is that record. It exists so the decision cannot be argued
backwards from whatever the experiment happens to produce.

Nothing has been measured. Every number below is a commitment, not a finding.

---

## The constraint these thresholds assume

No human at Verumetric touches a customer's job. Humans build gold sets and
audit the verifier offline. All experiment arms run fully autonomously, with
humans scoring only afterward. **A threshold met with human rescue in the loop
is a failed threshold.**

## Pre-registered setup

Fixed before any provider is called:

- **~500 pages**, two sources, stratified: ≥ 50% ugly (handwriting, phone
  photos, rotation, low resolution); ≥ 40% with totals/line items; ~10%
  deliberately without totals, to measure the recall problem. Counterpart
  documents required for ≥ 60% of pages.
- **4–5 providers across ≥ 3 distinct lineages**, one an open-weights engine run
  in-house. The premium verifier is a frontier multimodal model, always
  region-scoped.
- **One reference OCR layer** with word boxes over all pages. Every provider's
  output is grounded against it. This layer is ours; providers never see it, nor
  the gold, nor the canaries.
- **Gold: 150 pages**, two annotators working from page image + reference layer,
  **never from provider output**; disagreements adjudicated; inter-annotator
  agreement reported. Per-field consequence values assigned with each document
  source.
- **Six arms**, all autonomous: best fixed provider; cheapest fixed provider;
  machine-only cascade; predictive routing from cheap page features; predictive
  + cascade; oracle (post-hoc ceiling). Plus field-level ensemble, for
  information.
- **Budget ≤ $1,000.**

## T1–T11

"Important fields" = money, identifiers, quantities, dates, and any field the
customer marks critical. Measured on gold, on the simulated autonomous pipeline,
after the cascade.

| Test | Experiment-scale threshold | Production target |
|---|---|---|
| **T1** Automated coverage | ≥ 90% of important fields reach PASS or a resolved FAIL/RETRY; ≥ 85% of money fields auto-PASS | ≥ 95% / ≥ 92% |
| **T2** Residual error (money/ID) | Point estimate ≤ 0.5%, 95% UB ≤ 1.5% among auto-PASSED | UB ≤ 0.1% after 3,000 audited fields |
| **T2b** Residual error (all important fields) | ≤ 1%, UB ≤ 2% | UB ≤ 0.3% |
| **T3** Premium-verifier usage | ≤ 10% of important fields reach Tier 3; ≤ 3% reach Tier 4; ≤ 2% of *pages* reprocessed whole | ≤ 5% / ≤ 1.5% / ≤ 1% |
| **T4** Unresolved rate | ≤ 5% of important fields; ≤ 3% of money fields end UNVERIFIED | ≤ 3% / ≤ 1.5% |
| **T5** Cost | Verification + retries ≤ $0.04/page, **and** ≤ 10% of the per-page human review cost the customer reports | ≤ $0.03/page |
| **T6** Latency | Verification P95 ≤ 1.5× extraction P95 per document; 1,000-page batch end-to-end P95 ≤ 15 min with parallelism | ≤ 1.2× |
| **T7** Cascade economics | Machine-only cascade beats best fixed provider by ≥ 15% on expected total cost at equal-or-lower residual, **or** cuts residual by ≥ 30% at equal-or-lower cost | maintain |
| **T8** Customer acceptance | ≥ 3 of 8 qualified prospects accept "auto-verified, measured residual X ± CI, UNVERIFIED → null/exception" **without** asking for human review; ≥ 1 paid pilot | churn < 10%/yr on this basis |
| **T9** Ambiguity floor | ≤ 15% of gold money fields are single-source, no reconciliation, and low-quality crop | document-class gating |
| **T10** Lineage independence | ≥ 3 lineages with pairwise error-correlation φ < 0.3 on gold errors; if the best pair is > 0.5, "independent consensus" is fiction | refresh monthly |
| **T11** Calibration | Predicted P(wrong) vs observed, in deciles, within ±50% relative (predicted 1% → observed 0.5–1.5%) | ±25% |

## Decision rule

- **GO** — T1, T2, T3, T4, T5, T8, T10, T11 pass **and** T7 passes. Build the
  autonomous verified-extraction product on this document class.
- **PIVOT A — narrower field scope** — T2/T4 fail *only* on MAYBE-class fields
  (names, free text, handwritten single-source). Ship with those policy-gated to
  low-confidence/null; the YES-class fields carry the product.
- **PIVOT B — verification without cascade** — T7 fails but the rest pass. One
  engine plus independent machine verification is still the product; routing is
  off the roadmap until providers diverge again.
- **PIVOT C — add reconciliation inputs** — T1/T4 fail because customers didn't
  supply counterpart documents or master data, and the ambiguity floor (T9) is
  high. Re-run with POs/BOLs/vendor lists in scope; if coverage recovers, those
  inputs become a condition of service.
- **PIVOT D — different document class** — T9 fails hard (irreducible ambiguity
  dominates) and T3 shows premium usage > 25%. This population is not
  machine-verifiable; find one with invariants.
- **KILL** — T8 fails (customers demand human review from us regardless),
  **or** T2 fails on YES-class money fields even after cascade and Tier 4
  (residual UB > 3%), **or** T3 shows > 40% of important fields reaching Tier 3
  (verification has become re-execution).

## Kill signals

Written down before running. Any one of these ends the experiment early:

1. Tier 3 usage > 40% of important fields.
2. Money-field residual UB > 3% after cascade.
3. Ambiguity floor > 30%.
4. Zero of eight prospects accept the STP framing.

## Rule of three — what this experiment cannot prove

Residual error is measured on the auto-PASSED fields in the gold set. If zero
errors are observed among *n* adjudicated passed fields, the 95% upper bound on
the residual rate is ≈ 3/*n*.

| Claim | Adjudicated passed fields needed (zero errors observed) |
|---|---|
| residual ≤ 1% (99%) | ~300 |
| residual ≤ 0.5% (99.5%) | ~600 |
| residual ≤ 0.1% (99.9%) | ~3,000 |
| residual ≤ 0.01% (99.99%) | ~30,000 |
| residual ≤ 0.001% (99.999%) | ~300,000 |

If *any* errors are observed, the bound is wider still.

A 150-page gold set yields roughly 300–600 money/ID fields and 1,500–4,500
fields total. The experiment can support "money-field residual ≤ ~1% (95% UB)"
and "all-field residual ≤ ~0.2% (95% UB)". **It cannot support 99.99% on invoice
totals.** That is a production-audit claim: at 1,000 pages/day and a 0.5% audit
rate, ~15 money fields/day are adjudicated and n = 3,000 arrives in about seven
months.

Binding consequences for how any result may be reported:

- Every published residual carries its period, effective *n*, epoch identifier,
  confidence interval, and methodology version. A number without an epoch is a
  rumor.
- The coverage-vs-residual curve is estimable down to ~0.5% residual on money
  fields and ~0.1% overall. **Below that it is extrapolated from the posterior
  model and must be labeled as such** on every chart and in every
  customer-facing report.
- For the 99.999% class (bank routing numbers), the honest first-year product is
  "checksum + provenance + independent reread + master-data match, residual not
  yet measurable below 0.3%," and customers who need better keep their existing
  control.
- Gold-set noise is budgeted: double annotation with adjudication of
  disagreements, and inter-annotator agreement reported. If humans agree on
  < 97% of fields, that is the accuracy ceiling and the providers' "errors" are
  partly not errors.

## Open items in this pre-registration

Recorded now, before data, so they cannot be quietly resolved later in whichever
direction the results favor. Resolving one of these is an amendment (see below),
permitted only while no data exists for the affected test.

1. **T2b, T6 and T9 do not appear in the GO condition** as part-3 §6 writes it,
   though T9 appears in PIVOT D and in the kill signals. Decide explicitly
   whether a GO survives a T6 (latency) or T2b failure.
2. **T5's second clause needs a customer number.** "≤ 10% of the per-page human
   review cost the customer reports" cannot be evaluated until each document
   source states its current per-page cost. Collect it in the same session that
   assigns per-field consequence values.
3. **T8 is a sales test, not a measurement test**, and it is the sole
   unconditional KILL. It requires eight *qualified* prospects; "qualified" must
   be defined in writing before the first demo.
4. **T11's deciles need a minimum bin count.** At experiment scale several
   deciles will be sparse. Decide the minimum adjudicated fields per bin that
   counts as a pass.

## Amendment policy

This file may be amended **only before results exist for the affected test**,
and any amendment must state what changed, why, and on what date, with the prior
text preserved in git history. Once data exists for a test, its threshold is
frozen. Thresholds are not renegotiated to convert a failure into a pivot.
