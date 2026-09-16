# Pre-registered thresholds

**Status:** Pre-registration. Committed before the first full run. Not
renegotiated after seeing data.
**Date:** 2026-09-16
**Source:** `CLAUDE.md` §7, verbatim.

The body of this file is §7 as written. The appendix is commentary added while
committing it; nothing in the appendix alters a threshold.

---

## Thresholds

| Test | Threshold at experiment scale |
|---|---|
| T1 Coverage | ≥ 90% of important fields reach PASS or resolved FAIL/RETRY; ≥ 85% of money fields auto-PASS |
| T2 Residual (money/ID) | point ≤ 0.5%, 95% UB ≤ 1.5% among auto-PASSED |
| T2b Residual (all important) | ≤ 1%, UB ≤ 2% |
| T3 Premium usage | ≤ 10% of important fields reach Tier 3; ≤ 3% reach Tier 4; ≤ 2% of pages reprocessed whole |
| T4 Unresolved | ≤ 5% of important fields; ≤ 3% of money fields |
| T5 Cost | verification + retries ≤ $0.04/page and ≤ 10% of the per-page human review cost the customer reports |
| T6 Latency | verification P95 ≤ 1.5× extraction P95 per doc; 1,000-page batch P95 ≤ 15 min with parallelism |
| T7 Cascade | cascade beats best fixed by ≥ 15% expected total cost at equal-or-lower residual, or cuts residual ≥ 30% at equal-or-lower cost |
| T8 Customer acceptance | ≥ 3 of 8 prospects accept auto-verified output with stated residual and null-on-unverified, without demanding human review; ≥ 1 paid pilot (Tanner runs this) |
| T9 Ambiguity floor | ≤ 15% of gold money fields are single-source + no reconciliation + low-quality crop |
| T10 Lineage independence | ≥ 3 lineages with pairwise error correlation φ < 0.3 |
| T11 Calibration | predicted vs observed P(wrong) within ±50% relative per decile |

**Pre-registered kill signals:** Tier 3 usage > 40% of important fields;
money-field residual UB > 3% after cascade; ambiguity floor > 30%; 0 of 8
prospects accept the STP framing.

**Statistical honesty:** rule of three — zero errors in n audited passed fields
gives a 95% UB of ~3/n. With ~300–600 gold money fields we can support "≤ ~1%,"
not 99.99%. Report every residual with its n and UB. Never print a residual
without an interval.

---

## Appendix — commentary, not thresholds

### The constraint these thresholds assume

No human at Verumetric touches a customer job. All six arms run start to finish
autonomously; humans create gold and score arms afterward. **A threshold met
with human rescue in the loop is a failed threshold.**

### Decision rule (from `docs/critique/part-3.md` §6)

§7 lists the thresholds; the branch they feed is in part-3:

- **GO** — T1, T2, T3, T4, T5, T8, T10, T11 pass **and** T7 passes.
- **PIVOT A — narrower field scope** — T2/T4 fail *only* on MAYBE-class fields
  (names, free text, handwritten single-source). Ship with those policy-gated to
  low-confidence/null.
- **PIVOT B — verification without cascade** — T7 fails, rest pass. One engine
  plus independent machine verification is still the product.
- **PIVOT C — add reconciliation inputs** — T1/T4 fail for want of counterpart
  documents or master data, with a high ambiguity floor. Re-run with those in
  scope; if coverage recovers they become a condition of service.
- **PIVOT D — different document class** — T9 fails hard and Tier 3 usage
  exceeds 25%. This population is not machine-verifiable.
- **KILL** — T8 fails, **or** T2 fails on YES-class money fields even after
  cascade and Tier 4 (residual UB > 3%), **or** T3 exceeds 40% of important
  fields reaching Tier 3.

### Production targets (part-3 §6, for later — not experiment gates)

T1 ≥ 95% / ≥ 92% · T2 UB ≤ 0.1% after 3,000 audited fields · T2b UB ≤ 0.3% ·
T3 ≤ 5% / ≤ 1.5% / ≤ 1% · T4 ≤ 3% / ≤ 1.5% · T5 ≤ $0.03/page · T6 ≤ 1.2× ·
T8 churn < 10%/yr · T10 refreshed monthly · T11 ±25%.

### Open items

Recorded before data so they cannot be resolved later in whichever direction the
results favor. Each is an amendment (below), permitted only while no data exists
for the affected test.

1. **T2b, T6 and T9 are absent from the GO condition** as part-3 §6 writes it,
   though T9 drives PIVOT D and a kill signal. Decide explicitly whether a GO
   survives a T6 or T2b failure.
2. **T5's second clause needs a customer number** — "≤ 10% of the per-page human
   review cost the customer reports" is unevaluable until each document source
   states its current per-page cost. Collect it alongside the consequence values
   in `config/consequences.yaml`.
3. **T8 is a sales test and the sole unconditional KILL.** It needs eight
   *qualified* prospects; define "qualified" in writing before the first demo.
4. **T11's deciles need a minimum bin count.** Several deciles will be sparse at
   experiment scale. Decide the minimum adjudicated fields per bin that counts.

### Amendment policy

Amendable **only before results exist for the affected test**, stating what
changed, why, and on what date, with the prior text preserved in git history.
Once data exists for a test, its threshold is frozen. Thresholds are not
renegotiated to convert a failure into a pivot.
