# Agent Commerce Layer — Critique, Part 3: Machine-Only Verification

*September 15, 2026. The constraint: no human in the production path. Humans build gold and audit the verifier; they never touch a customer's job.*

---

## Direct answer to the hard question

> Can a machine-only verification stack realistically achieve commercially acceptable trust without simply rerunning the entire job through an equally expensive model?

**Yes, for a specific and identifiable class of work; no for most of what people call "AI work"; and even in the yes class, there are two failure modes the ladder cannot escape and one measurement limit you must accept before running the experiment.**

The yes class is work whose output is a set of *claims* that are each (a) **localized** to evidence the verifier can inspect without redoing the search, (b) **constrained** by invariants the output must satisfy, or (c) **checkable against an external oracle** the worker didn't have. Invoice extraction with line items and a PO is all three. Creative writing is none.

The two escapes the ladder can't make:

1. **Completeness (recall) is symmetric.** "Did the worker miss a line item?" cannot be verified by inspecting the claims the worker made; it requires knowing what the document contains, which is the job. Arithmetic rescues this on documents with totals (a missed line makes the sum fail). On documents without totals (packing lists, timecards, some tickets), recall verification requires a structural pass over the page — cheaper than full extraction, but not local.
2. **Irreducible ambiguity.** A smudged "3" that might be an "8", a single-source handwritten field, no counterpart document, no arithmetic. Every machine tier sees the same pixels; more models don't create information. The only honest output is UNVERIFIED. The commercial question is what fraction of high-value fields fall here, and that fraction is a property of the customer's documents, not of your stack.

The measurement limit: **you cannot demonstrate 99.99% residual accuracy with a 150-page gold set.** Details in §5. Thresholds must be stated as confidence-interval upper bounds, and the tightest classes (bank numbers at 99.999%) are provable only after months of production audits, not in the experiment.

With that said: the numbers you sketched (82% deterministic, 13% provenance, 4% cheap model, 0.9% premium, 0.1% unresolved) are plausible for invoice-class documents with reconciliation. They are not plausible for single-source handwritten forms. The experiment's job is to find out which population you have.

---

## 1. Why verification is asymmetric (and when it isn't)

Four sources of asymmetry, in order of strength:

| Source | What it means | Example | Cost of check vs cost of work |
|---|---|---|---|
| **Invariants** | The output must satisfy constraints the worker had to *discover* but the verifier only has to *evaluate* | line items sum to subtotal; tax = rate × base; qty × price = extended | ~0 vs full extraction |
| **External oracles** | A source of truth outside the document | PO in the ERP; carrier in master data; counterpart BOL; unit tests | one lookup vs full extraction |
| **Locality** | Each claim points at a small region; the verifier inspects the region, not the document | invoice_total → crop on page 3 | 1–2% of tokens vs 100% |
| **Recomputation** | Some claims can be recomputed from the output itself | derived totals, unit conversions, date arithmetic | ~0 |

And the two symmetric cases:

| Symmetric case | Why | Mitigation |
|---|---|---|
| **Completeness / recall** | Verifying absence requires enumerating presence | invariants (sums), structural row counts from the reference layer, counterpart-document line counts |
| **Judgment** | No invariant, no oracle, no location — "is this summary good?" | none; not in scope |

The design principle follows: **a field passes only on positive evidence that would have failed had the value been wrong.** A type check passing is not evidence of correctness; a reconciliation passing is. Distinguish *confirming* checks from *rejecting-only* checks in the ladder (§3).

---

## 2. Task classes: YES / MAYBE / NO

### YES — asymmetric, cheap, machine-only viable now
- **Structured extraction with reconciliation:** invoices with line items, freight invoices vs BOL/PO, receipts with totals, statements with balances. Invariants + oracles + locality all present.
- **Cross-document reconciliation itself:** three-way match, bank-to-ledger, manifest-to-shipment. The output *is* an invariant check; verification is recomputation.
- **Data transformations with invariants:** row counts, checksums, referential integrity, schema conformance, idempotency tests.
- **Calculations:** recompute from inputs.
- **Normalization against reference tables:** addresses, product codes, carrier codes, units — the reference table is the oracle.
- **Code generation with executable tests** *where the tests were not written by the worker.* Tests are an oracle; the asymmetry is real. Caveat: test coverage is the coverage ceiling, and test-gaming is an adversarial concern once workers are external.
- **Deduplication / matching with keys:** verifiable by key recomputation.

### MAYBE — asymmetric only under conditions
- **Extraction of single-source fields without reconciliation:** names, addresses, free-text on forms. Locality helps (crop reread); no invariant, no oracle. Viable when image quality is good and lineages are independent; degrades to UNVERIFIED on bad scans. Coverage will be lower than the YES class; measure it separately.
- **Transcription with timestamps:** locality exists (re-listen to the segment); forced-alignment scores and language-model perplexity are weak invariants; no oracle. Numbers, names, and codes in speech are the risky fields. Viable for structured audio (call metadata, dictated forms), weak for free conversation.
- **Classification:** verifying a label usually means reclassifying (symmetric) — unless consistency constraints exist (a "freight invoice" must have a carrier and weight; a document classified as "PO" must contain a PO number). Viable when the taxonomy has checkable structure.
- **Table extraction without totals:** locality yes; recall check requires structural row detection from the reference layer. Viable with a cheap structural pass.
- **Handwriting-heavy forms:** locality yes, but irreducible ambiguity dominates; coverage may be 60–80% rather than 95%. Still commercially useful if the exception stream is small enough (see §7).

### NO — symmetric or judgment-bound
- **Creative writing, strategy, design, aesthetic judgment:** no invariant, no oracle, no location.
- **Open-ended research and "find everything about X":** completeness over an unbounded space; verification is redoing the search.
- **Summarization:** faithfulness checks exist (claim-level entailment against the source is locality-like), but completeness and salience are judgment. Faithfulness-only verification is a MAYBE; "good summary" is a NO.
- **Translation:** back-translation is a weak, correlated check; fluency and fidelity are judgment. Terminology-against-glossary is the only oracle. NO for the first company.
- **Physical-world tasks:** verification requires sensors you don't have.
- **Anything where the worker chooses the schema:** if the output's structure is itself a judgment, invariants can't be defined in advance.

**The first company lives in YES, with MAYBE-class fields handled by policy (null/low-confidence), and never touches NO.** That sentence should be in the company's one-pager.

---

## 3. The machine-only evidence stack, redesigned

Your ladder is right in shape. Three changes: (a) treat it as Bayesian evidence accumulation with a stopping rule, not a sequence of gates; (b) separate confirming from rejecting-only checks; (c) scope Tiers 3–4 to disputed *regions*, so they never become "rerun the job."

### The object being verified
Each field claim: `{value, provenance{type, page, bbox, source_text}, field_class, consequence}` where `consequence` is the customer-assigned cost of an undetected error (money fields carry their value; identifiers carry a policy constant).

### The prior
P(correct) before any check = the performance graph's calibrated estimate for (provider, epoch, field_class, document features). A new provider on a new document class starts at a deliberately pessimistic prior, which forces more evidence gathering — exactly the behavior you want.

### Evidence items
Each check contributes a likelihood ratio, estimated from gold and updated by offline audits. Illustrative magnitudes (the experiment calibrates them):

**Tier 0 — deterministic, free**
- *Rejecting-only:* type/format/range validity; date sanity; identifier checksums (ABA routing has a check digit; VINs; IBANs; some PO schemes). These set P(correct)=0 on failure and barely move it on success.
- *Confirming:* arithmetic reconciliation (sum of lines = subtotal; subtotal + tax + freight = total; qty × price = extended); cross-field consistency; duplicate detection against prior jobs; business rules against master data (vendor exists, PO open, carrier valid, rate in contract range); **counterpart-document match** (invoice vs PO vs BOL). A total that survives both intra-document arithmetic and PO match has a likelihood ratio in the hundreds.
- *Value-source agreement:* `value` parses from `source_text` (catches transcription-to-number errors). Rejecting-only but very sharp.

**Tier 1 — provenance grounding, near-free**
- Claimed page/bbox exists; `source_text` fuzzy-matches the reference OCR layer's words at that location (string similarity ≥ threshold); the reference layer's own read of the region agrees with `value` after normalization. Confirming, moderate strength — the reference layer is a (weak, but independent-lineage) second reader for free.
- Multi-occurrence agreement: if the value appears in several places (page 1 header and page 3 total), agreement is confirming; disagreement is a strong flag.

**Tier 2 — cheap independent crop reread**
- A different-lineage engine reads only the crop (plus a small margin). Agreement is confirming with strength weighted by estimated lineage independence; disagreement is *information* — it raises the field's risk and routes it up the ladder, it does not decide.
- Cost: cents per hundred crops.

**Tier 3 — strong model on the disputed region**
- A premium multimodal model reads the disputed field's page region (not the packet), with the two candidate values and the reconciliation context ("line items sum to X; candidates are 18,381.16 and 18,331.16; which does the image show?"). Confirming, strong, and — importantly — not correlated with the OCR-lineage engines in the way two OCR engines are. Scope it to the region; if you find yourself sending whole documents here more than a few percent of the time, the asymmetry has failed for that document class.

**Tier 4 — redundant region reprocessing with lineage-aware accumulation**
- Two or three additional independent engines on the region or page; evidence combined by weighted likelihood ratios using the empirical error-correlation matrix between lineages (estimated from gold: for each pair, the phi coefficient of their error indicators). Correlated agreement counts once; independent agreement counts fully. Never a vote.
- Recall repair belongs here: if reconciliation fails because a line is missing, a structural row-count from the reference layer identifies which region was skipped; reprocess that region only.

**Stopping rule (this replaces "if sufficient: PASS")**
After each check, compute posterior P(wrong). Stop and PASS when P(wrong) × consequence < cost of the cheapest remaining check that could plausibly change the decision. Stop and FAIL/RETRY when P(wrong) exceeds the retry threshold for the field class. Stop and UNVERIFIED when all checks are exhausted or when the expected value of further evidence is below its cost (i.e., the remaining checks are all correlated with what's been done). The customer's policy maps UNVERIFIED to null / low-confidence / retry-with-another-provider / reject-batch.

Effect of this rule: a $12.37 shipping charge that passes arithmetic stops at Tier 0. A $250,000 total with no PO match and a Tier 2 disagreement keeps climbing until the premium model resolves it or it's marked UNVERIFIED. A bank routing number always gets at least checksum + provenance + independent crop reread regardless of prior, because its consequence constant is set high. This is your "value-at-risk sets verification depth," implemented as one inequality.

### Cascade integration
The cascade is the same machine: when a *document* accumulates too many FAIL/UNVERIFIED fields (or any FAIL on a critical field) relative to its provider's expected behavior, resubmit the document — or the failing regions — to the next provider. Verification results from the first pass are evidence for the second (a field that two providers independently read identically, and that reconciles, is done). Cascade depth is bounded by policy and budget.

### What disagreement does
Exactly what you said: it sets risk, it never decides. In the ladder, a Tier 2 disagreement on a money field is treated as a strong likelihood ratio *toward wrong for both candidates* until further evidence arrives; arithmetic or counterpart match then typically singles one out at zero cost, and the premium model resolves the remainder.

---

## 4. Humans audit the verifier

The offline audit is not a random 0.5% sample. It is stratified to learn the most per adjudicated field:

- **Random baseline:** 0.3–0.5% of auto-PASSED fields, uniformly. This is the only unbiased estimate of residual error; nothing else can be reported as "measured residual."
- **Least-margin oversample:** PASSED fields whose posterior was closest to the threshold. Catches calibration error where it matters.
- **Provenance-only passes:** fields that passed on Tier 1 evidence alone (no reconciliation, no oracle). Highest structural risk.
- **New epochs / new providers / new customers / new document classes:** elevated rates until effective n is adequate.
- **Disagreement-resolved fields:** anything where Tier 3/4 overrode a lower tier.
- **Unverified sample:** a slice of UNVERIFIED fields, to measure how often the machine was too conservative (informs threshold tuning and the customer's exception cost).

Outputs of the audit, monthly: residual error by field class with confidence interval; calibration curve (predicted vs observed P(wrong)); lineage correlation matrix refresh; drift flags. These update the likelihood ratios and the prior model. They are also the substance of the trust product: the number you publish is the number the audit measured, with its interval and its effective n. That is what "verified automatically with X measured residual error" means, and it is defensible only because humans never touched the jobs.

---

## 5. Statistical power: what the experiment can and cannot prove

Residual error is measured on the auto-PASSED fields in the gold set. Use the rule of three: if you observe zero errors among n adjudicated passed fields, the 95% upper bound on the residual rate is ≈ 3/n.

| Claim you want to make | Adjudicated passed fields needed (zero errors observed) |
|---|---|
| residual ≤ 1% (99%) | ~300 |
| residual ≤ 0.5% (99.5%) | ~600 |
| residual ≤ 0.1% (99.9%) | ~3,000 |
| residual ≤ 0.01% (99.99%) | ~30,000 |
| residual ≤ 0.001% (99.999%) | ~300,000 |

If you observe *some* errors, the bound is wider still.

A 150-page gold set yields roughly 300–600 money/identifier fields and 1,500–4,500 fields total. So the experiment can support claims like "money-field residual ≤ ~1% (95% UB)" and "all-field residual ≤ ~0.2% (95% UB)". It cannot support 99.99% on invoice totals. That claim is a production-audit claim: at 1,000 pages/day with a 0.5% audit rate, you adjudicate ~15 money fields/day and reach n=3,000 in about seven months.

Consequences for the design:
- Thresholds in §6 are stated as CI upper bounds at experiment scale, with tighter production targets stated separately.
- The **coverage-vs-residual curve** is estimable at experiment scale for residual levels down to ~0.5% on money fields and ~0.1% overall; below that the curve is extrapolated from the posterior model, and you must label it as such.
- For the 99.999% class (bank numbers), the honest product for the first year is "checksum + provenance + independent reread + master-data match, residual not yet measurable below 0.3%," and customers who need better keep their existing control. You are not lying to them; you are the first vendor telling them the truth.

Also budget for **gold-set noise**: double annotation with adjudication of disagreements; report inter-annotator agreement. Annotators must work from the page image and the reference OCR layer, *never* from provider output, or the gold inherits the providers' errors.

---

## 6. Revised GO / PIVOT / KILL — machine-only production

All measured on gold, on the *simulated autonomous* pipeline, after the cascade, with humans only scoring afterward. "Important fields" = money, identifiers, quantities, dates, and any field the customer marks critical.

| Test | Threshold at experiment scale | Production target (after audits) |
|---|---|---|
| **T1 Automated coverage** | ≥ 90% of important fields reach PASS or a resolved FAIL/RETRY; ≥ 85% of money fields auto-PASS | ≥ 95% / ≥ 92% |
| **T2 Residual error (money/ID)** | Point estimate ≤ 0.5%, 95% UB ≤ 1.5% among auto-PASSED | UB ≤ 0.1% after 3,000 audited fields |
| **T2b Residual error (all important fields)** | ≤ 1%, UB ≤ 2% | UB ≤ 0.3% |
| **T3 Premium-verifier usage** | ≤ 10% of important fields reach Tier 3; ≤ 3% reach Tier 4; ≤ 2% of *pages* are reprocessed whole | ≤ 5% / ≤ 1.5% / ≤ 1% |
| **T4 Unresolved rate** | ≤ 5% of important fields; ≤ 3% of money fields end UNVERIFIED | ≤ 3% / ≤ 1.5% |
| **T5 Cost** | Verification + retries ≤ $0.04/page, and ≤ 10% of the per-page human review cost the customer reports | ≤ $0.03/page |
| **T6 Latency** | Verification P95 ≤ 1.5× extraction P95 per document; 1,000-page batch end-to-end P95 ≤ 15 min with parallelism | ≤ 1.2× |
| **T7 Cascade economics** | Machine-only cascade beats best fixed provider by ≥ 15% on expected total cost at equal-or-lower residual, **or** cuts residual by ≥ 30% at equal-or-lower cost | maintain |
| **T8 Customer acceptance** | ≥ 3 of 8 qualified prospects accept "auto-verified, measured residual X ± CI, UNVERIFIED → null/exception" **without** asking you to add human review; ≥ 1 paid pilot | churn < 10%/yr on this basis |
| **T9 Ambiguity floor** | ≤ 15% of gold money fields are single-source, no reconciliation, and low-quality crop (the irreducible class) | document-class gating |
| **T10 Lineage independence** | ≥ 3 lineages with pairwise error-correlation φ < 0.3 on gold errors; if the best pair is > 0.5, "independent consensus" is fiction | refresh monthly |
| **T11 Calibration** | Predicted P(wrong) vs observed, in deciles, within ±50% relative (e.g., predicted 1% → observed 0.5–1.5%) | ±25% |

**Decision:**
- **GO:** T1, T2, T3, T4, T5, T8, T10, T11 pass and T7 passes. Build the autonomous verified-extraction product on this document class.
- **PIVOT A — narrower field scope:** T2/T4 fail *only* on MAYBE-class fields (names, free text, handwritten single-source). Ship with those fields policy-gated to low-confidence/null; the YES-class fields carry the product.
- **PIVOT B — verification without cascade:** T7 fails but the rest pass. One engine plus independent machine verification is still the product; routing is off the roadmap until providers diverge again.
- **PIVOT C — add reconciliation inputs:** T1/T4 fail because customers didn't supply counterpart documents or master data, and the ambiguity floor (T9) is high. Re-run with POs/BOLs/vendor lists in scope; if coverage recovers, the product requires those inputs as a condition of service.
- **PIVOT D — different document class:** T9 fails hard (irreducible ambiguity dominates) and T3 shows premium usage > 25%. This population is not machine-verifiable; find one with invariants.
- **KILL:** T8 fails (customers demand human review from you regardless), **or** T2 fails on YES-class money fields even after cascade and Tier 4 (residual UB > 3%), **or** T3 shows > 40% of important fields reaching Tier 3 (verification has become re-execution).

Thresholds fixed before data; recorded in the repo; not renegotiated.

---

## 7. What "replace human review" honestly means

Machine-only verification produces two streams: a **certified stream** (auto-PASSED, with measured residual) and an **exception stream** (FAIL/UNVERIFIED, returned as null or low-confidence). The customer's existing exception process handles the second. This is straight-through processing, the same shape as payments and claims automation, where STP rates of 85–95% are considered excellent and the remaining exceptions are a normal cost center.

So the claim is not "no human ever looks at a field." It is "no human at *our* company touches your job, and the fraction of *your* fields that need a human drops from 100% to (1 − coverage), with the residual error in the certified stream measured and published." T4 is what makes the exception stream commercially tolerable; T8 is whether customers believe the measurement. If T8 passes, you have the product; if it fails, the market wants a human signature more than it wants the math, and no architecture fixes that.

---

## 8. Attack summary — how machine-only fails in the first category

1. **The document population is mostly single-source and ugly** (T9). Then coverage on money fields might be 70%, the exception stream is a third of the work, and the customer's savings shrink to the point where T7/T8 fail. Mitigation: require counterpart documents as inputs (PIVOT C); choose customers whose paper reconciles.
2. **Recall failures dominate** on documents without totals. Verification becomes page-level structural work; cost rises; T3/T5 fail. Mitigation: prefer document classes with sums; build the structural row-count pass early.
3. **Lineages aren't independent** (T10). Two "different" providers share a backbone, agree on the same misread, and Tier 2/4 evidence is inflated. Residual error is then underestimated until the audit catches it — which is why the random audit is non-negotiable. Mitigation: at least one lineage that is a general multimodal LLM rather than an OCR pipeline, and one open-weights engine you control.
4. **Calibration drifts silently** on a new customer's documents (T11). The posterior says 99.5% and reality is 97%. Mitigation: pessimistic priors for new (provider × doc class) cells, elevated audit rates until effective n is adequate, epoch detection.
5. **Premium tier creep.** Engineers "fix" false rejects by escalating more; Tier 3 usage drifts from 5% to 30% and the economics quietly become "run the job twice" (T3). Mitigation: T3 is monitored in production as a first-class metric with an alert.
6. **Customers won't accept a measurement in place of a signature** (T8). Some industries (regulated finance, healthcare) have controls that require human attestation regardless of measured error. Mitigation: stay in verticals where the current control is an office manager, not a compliance officer — which is the construction/freight choice again.
7. **Adversarial workers** (later, when providers are external). A provider can learn to emit outputs that satisfy invariants (fabricated line items that sum). Mitigation: provenance grounding against your own reference layer is the only check a worker can't satisfy without reading the document correctly; keep that layer yours and never let workers see the gold or canaries.

None of these are reasons not to run the experiment. All of them are things the experiment must measure.

---

## 9. The redesigned experiment (≤ $1,000, 3–4 weeks)

**Purpose:** decide whether a fully autonomous evidence stack can certify a commercially useful fraction of important fields at a measurable residual error on one YES-class document population, and produce the coverage-vs-residual curve.

**Documents (500 pages):**
- Two sources: a trades/mining contractor (material and delivery tickets, supplier invoices, ideally with matching POs or job-cost entries) and a freight broker (carrier invoices with matching BOLs/PODs/rate confirmations). Counterpart documents are *required* for at least 60% of pages; that's the reconciliation oracle.
- Stratify: ≥ 50% ugly (handwriting, phone photos, rotation, low resolution); ≥ 40% with totals/line items; ~10% deliberately without totals to measure the recall problem.

**Providers (4–5, ≥ 3 lineages):** one cloud OCR-native (Textract or Document AI or Azure DI), one LLM-native extractor (a frontier multimodal model prompted for the schema), one specialist/newer OCR (Mistral OCR or similar), one open-weights engine you run (so at least one lineage is under your control and free to call). Premium verifier: a frontier multimodal model, region-scoped.

**Reference layer:** one cheap word-box OCR pass over all 500 pages. Ground every provider's output to it.

**Gold (150 pages, ~300–600 money/ID fields, ~1,500–4,500 fields total):** two contractors annotate from page image + reference layer, never from provider output; adjudicate disagreements; report inter-annotator agreement. Assign per-field consequence with each document source (30 minutes each). ~$400–600.

**Code (scripts, ~1–2 weeks):** provenance/evidence schema; Tier 0 checks including reconciliation against counterpart docs and a small master-data table; Tier 1 grounding; Tier 2 crop reread; Tier 3 region-scoped premium call; Tier 4 lineage-aware accumulation; the stopping rule with per-field-class consequence; cascade controller. Log every check, cost, and latency per field.

**Arms, all fully autonomous (no human rescue):**
1. Best fixed provider, verification on.
2. Cheapest fixed provider, verification on.
3. Machine-only cascade.
4. Predictive routing from cheap page features (blur, skew, handwriting fraction, table density, class).
5. Predictive + cascade.
6. Oracle (per-document best provider, computed after the fact from gold — the ceiling).
Plus, for information: field-level ensemble (best engine per field), to see whether the ensemble ceiling beats routing.

**Outputs:**
- Coverage-vs-residual curve per field class per arm, produced by sweeping the posterior threshold; annotate the region below ~0.5% residual as extrapolated.
- Escalation-depth histogram (share of fields resolved at Tiers 0/1/2/3/4/unresolved) and share of *pages* reprocessed whole.
- Cost per 1,000 fields by tier; verification cost per page; latency P50/P95.
- Lineage error-correlation matrix (T10).
- Calibration table (T11).
- Ambiguity floor (T9): share of money fields that are single-source, no reconciliation, low-quality crop.
- Recall analysis: on the no-totals subset, how often lines were missed and whether the structural row count caught it.
- Per-arm T1–T7 results; a one-page STP report per document source ("certified 91.4% of money fields, residual 0.6% (UB 1.4%), exceptions 8.6%, cost $0.11/page").

**Customer step (T8):** show each source their own STP report, state plainly that no human at your company reviewed their documents, and ask for a paid pilot. Extend to five more prospects with the same report format.

**Budget:** API calls across tiers and arms ~$150–250; premium verifier ~$30–80 (region-scoped, tail only); gold ~$400–600; open-weights engine on a rented GPU hour or two ~$10. Total ≤ $1,000.

**Pre-registered kill signals** (write them down before running): Tier 3 usage > 40% of important fields; money-field residual UB > 3% after cascade; ambiguity floor > 30%; zero of eight prospects accept the STP framing.

---

## 10. What this changes about the company

- The product is a **straight-through-processing certifier** for a class of documents, not an extraction service and not a marketplace. Its two published numbers per customer are STP rate and audited residual error.
- The moat is the calibrated evidence model, the lineage correlation matrix, the reference layer, and the audit history — all of which exist only because no human sat in the path (otherwise the numbers describe the humans, not the machine).
- The escalation ladder is the router. Predictive routing becomes a cost optimization on top, if arm 4/5 beats arm 3; otherwise it's dropped without regret.
- Task-category expansion follows verifiability, not TAM: next categories are the other YES-class rows in §2, each entered only after its own coverage-vs-residual curve is measured.
- The autonomous-commerce future, if it arrives, plugs into this at the top: a machine buyer accepts a certified stream with a published residual, exactly as a human buyer does today. If it doesn't arrive, the certifier still sells to office managers. The constraint you added didn't narrow the company; it defined it.
