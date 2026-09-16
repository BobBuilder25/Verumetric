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

§7 lists the thresholds; the branch they feed is in part-3. **Amendment 1
below supersedes the gating of T6, T2b and T5's second clause** — read it with
this list:

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

1. ~~**T2b, T6 and T9 are absent from the GO condition.**~~ **Settled by
   Amendment 1** (2026-09-16): T6 is measure-and-report, T2b routes to PIVOT A
   under a stated condition, T9 keeps its existing role in PIVOT D and the kill
   signals.
2. ~~**T5's second clause needs a customer number.**~~ **Settled by Amendment 1**:
   the second clause is non-gating and reported as "pending customer input"
   until each source reports its real per-page cost. The first clause still
   gates. One open question remains — see Amendment 1, note on T5.
3. **T8 is a sales test and the sole unconditional KILL.** It needs eight
   *qualified* prospects; define "qualified" in writing before the first demo.
4. **T11's deciles need a minimum bin count.** Several deciles will be sparse at
   experiment scale. Decide the minimum adjudicated fields per bin that counts.

---

## Amendment 1 — gating rulings

**Date:** 2026-09-16 · **By:** Tanner · **Status:** made before any data exists,
per the amendment policy below. **No threshold value changes.** What changes is
which tests gate the GO decision.

**Ruling principle.** *A test gates GO only if failing it means the thesis is
false. Tests that measure engineering quality get reported, not gated.*

### T6 (latency) — no longer a GO gate

Downgraded to **measure-and-report**. Latency is parallelism and caching, not a
thesis question. Record P50/P95 per the §6 outputs as before. If verification
P95 exceeds **3× extraction P95**, raise it as an engineering finding — not a
KILL, not a PIVOT.

### T2b (residual on all important fields) — conditional, routes to PIVOT A

Failing T2b alone does **not** block GO. On a T2b failure, decompose the excess
residual by field class:

- Excess concentrated in **party / text / single-source handwritten** fields →
  ship with those policy-gated to low-confidence/null and **GO on the YES-class
  fields**. This is PIVOT A, and it is a shipping decision, not a failure.
- Excess in **money, identifier, quantity or date** → that is T2 territory and
  it **gates**. A T2b failure carried by money or ID fields is a T2 failure
  wearing a wider denominator.

The decomposition must be computed and reported, never asserted.

### T5 (cost) — first clause gates, second clause cannot

- **≤ $0.04/page** — gates. If verification costs more than this, the economics
  the thesis rests on are not there.
- **≤ 10% of the customer's reported per-page human review cost** — **non-gating
  until a real customer figure exists.** `config/consequences.yaml` carries a
  $0.90 placeholder purely to keep the pipeline unblocked. Reports state
  "pending customer input" for this clause and print no pass/fail from the
  placeholder.

*Note — needs Tanner's confirmation:* the ruling as given lists T1, T2, T3, T4,
T8, T10, T11 as hard gates and does not mention T5. Read literally that drops
T5 entirely, which contradicts the ruling principle: verification that costs
more than the human work it replaces falsifies the commercial half of the
thesis. This amendment therefore keeps **T5's first clause as a gate**. If that
is wrong, correct it here before data exists.

### Gates after this amendment

| Gates GO | Reported, does not gate |
|---|---|
| T1, T2, T3, T4, T5 (first clause), T7, T8, T10, T11 | T2b (routes to PIVOT A under the condition above), T5 (second clause, pending), T6 |

T9 is unchanged: it does not gate directly, it drives PIVOT D and carries a kill
signal at > 30%. The four pre-registered kill signals are unchanged.

---

## Amendment 2 — testability on public corpora

**Date:** 2026-09-16 · **By:** Tanner · **Status:** made before any data exists.
**No pre-registered threshold value changes.** What changes is which tests this
particular run can evaluate at all.

The experiment runs on public real-document corpora — CORD (primary), SROIE
(secondary), FUNSD (no-totals subset) — because no customer documents exist yet
and synthetic documents cannot test the thesis: generating a page means
generating its answer. See ADR-0005.

### T8 (customer acceptance) — NOT TESTABLE here

T8 asks whether prospects accept auto-verified output with a stated residual.
Public corpora have no customer attached, so nothing in this run bears on it.

- T8 **remains a hard KILL gate.**
- It is **deferred to a separate customer step**, which Tanner runs.
- Therefore **a GO from this run is CONDITIONAL on T8.** No result from these
  corpora, however good, clears it. A run that passes everything else and is
  reported as "GO" without that qualifier is a misreport.

### T9 (ambiguity floor) — testable, with a population caveat

Measured on receipts: small, dense, often photographed, frequently single-source.
That population plausibly carries a **higher** ambiguity floor than construction
tickets backed by supplier statements, which are the intended commercial
population (ADR-0001, ADR-0003).

- Report the measured figure against the pre-registered 15% threshold and the
  30% kill signal, unchanged.
- **Flag the population difference wherever the number appears.** A T9 failure on
  receipts is not a verdict on the construction vertical — and a T9 *pass* on
  receipts is the stronger result, since it would clear a harder population.

### Testable as written

T1, T2, T2b, T3, T4, T5 (first clause), T6, T7, T10, T11.

### Carried forward from Amendment 1, unchanged

T6 is measure-and-report, not a gate. A T2b failure routes to PIVOT A when the
excess residual sits in party/text fields and gates when it sits in
money/identifier/quantity/date. T2 stays a hard gate. T5's second clause remains
pending customer input and cannot pass or fail on the placeholder.

### Two floors that constrain every number from this run

1. **Gold noise floor.** Published annotations are gold here, and they contain
   known errors. Tanner adjudicates a random 100-field slice; the measured
   annotation-error rate is reported. **If it exceeds 2%, it is folded into every
   residual as gold noise and stated explicitly.** No residual may be reported
   below the gold noise floor as though it were real — a 0.3% residual measured
   against 2%-wrong gold is not a residual, it is noise the instrument cannot
   resolve.

2. **Coverage is a LOWER BOUND.** No counterpart documents exist in these
   corpora, so cross-document reconciliation — the strongest confirming evidence
   in the stack — contributes nothing here. Counterpart evidence is logged
   UNAVAILABLE, never FAIL. `RESULTS.md` must state that real customer paper
   would raise measured coverage, and by an unknown amount.

### Contamination is a validity condition, not a metric

CORD and SROIE are almost certainly in the training data of the models under
test. All T-metrics are computed on the **augmented** run; the as-is minus
augmented delta per provider is reported as the contamination estimate. If that
delta is large, the as-is numbers are recitation, and any T-result quoted from
them is void.

### Amendment policy

Amendable **only before results exist for the affected test**, stating what
changed, why, and on what date, with the prior text preserved in git history.
Once data exists for a test, its threshold is frozen. Thresholds are not
renegotiated to convert a failure into a pivot.
