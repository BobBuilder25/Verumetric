# Agent Commerce Layer — Critique, Part 2

*September 15, 2026. Responses to sixteen challenges, an attack on the narrowed thesis, and a GO / PIVOT / KILL test.*

---

## The one reframe that changes everything below

Before the sixteen items, one correction to my own Part 1 and to your Experiment A framing.

**API cost is a red herring.** Extraction APIs cost $0.005–0.05 per page. Human data entry and review cost $0.50–2.00 per page. On an 8,000-page batch, oracle routing that cuts the API bill from $240 to $123 saves $117. A verification layer that lets the customer skip human review on 90% of fields instead of 60% saves $2,000–8,000 on the same batch.

So the thesis is not "buy machine work cheaper." It is: **"predict and detect provider failures well enough that the customer touches fewer fields by hand, with measured (not guaranteed) error rates."** Routing serves that goal by picking the provider that produces the fewest fields needing human attention on this document type. Cost per API call is a tiebreaker.

This means the oracle objective in the experiment must be:

> minimize ( API cost + human-review cost of flagged fields + expected cost of errors that pass )

not "minimize API cost at ≥ X% accuracy." Everything else in this document assumes that objective.

---

## 1. Customer product vs defensible core

Your distinction is right and I collapsed it too far. Restated:

- **What customers pay for:** evidence-backed structured data, fewer human touches, automatic failover, audit trail, vendor governance, region/policy enforcement.
- **What keeps customers and blocks copycats:** the verified-outcome ledger, the failure taxonomy, the calibrated context model, and the methodology's public reputation.

The rule for deciding which control-plane products to build: **build it only if it either (a) cannot work without the ledger, or (b) generates ledger data.** Apply it:

| Product | Needs ledger? | Feeds ledger? | Build/rent |
|---|---|---|---|
| Vendor selection / routing | Yes | Yes | Build |
| Verification | Is the ledger | Yes | Build |
| Automatic failover (cascade on verify-fail) | Yes | Yes | Build — it's free once verification exists |
| Audit trail / evidence export | Is a view of the ledger | — | Build (cheap) |
| Compliance routing (region, approved-vendor lists) | Partially | Yes (policy violations are outcomes) | Build as pure filters |
| Spend control / budgets / approvals | No | No | Rent (Nevermined/Natural/Stripe) or trivial DB fields |
| Procurement workflows (POs, approvals, contracts) | No | No | Don't build; integrate later |
| Provider benchmarking reports | Yes | — | Build once ledger is real |

Products in the top six are one product with different views; you're not losing them. Spend control and procurement workflow are where you'd have quietly rebuilt Ramp.

## 2. Simpler payments: agree, with two caveats

Yes. Operate as an ordinary B2B service for as long as possible. Upstream vendors are your vendors under your accounts; the customer's contract is with you; you invoice or charge a card on delivery. No Connect, no balances, no payouts, no chargeback loop, no transmission question. This is a service bureau with software inside, and it is exactly how you should start.

**Caveat 1 — you are now fronting upstream costs.** Between execution and payment you carry the vendor bill. At $0.01–0.05/page that's $80–400 per 8,000-page batch, bounded by a per-customer credit limit you set. Manage it like any SaaS: card on file with charge-on-delivery for new customers; net-15/30 invoicing with a credit limit for known ones; prepaid invoice (deposit) for a first large batch. This is normal trade credit, not job financing in the sense you feared.

**Caveat 2 — vendor terms.** Check each upstream provider's terms for (a) resale/embedding permissions (cloud vendors generally allow it), (b) benchmark-publication clauses (some restrict publishing comparative results without consent), (c) DPAs you must accept to send customer data. None is a blocker; all need reading before you publish a benchmark.

When does marketplace settlement become necessary? Only when a provider is someone you *can't* have an ordinary vendor account with — an independent specialist who wants per-job payouts and won't invoice you monthly. Even then: pay the first few as ordinary vendors on net-30 against your ledger. Stripe Connect enters when you have roughly ten external sellers or a seller who needs same-week payout. Not before.

## 3. Payment and legal architecture, done carefully

Verify current Stripe documentation before relying on the details below; the structure is stable, specifics change.

**Direct charges.** The charge is created on the connected (seller) account. The seller is merchant of record: their name on the statement, their responsibility for refunds and disputes, their negative balance if a dispute lands. Platform takes an application fee. Typically used with Standard accounts. Weak fit: you'd have no leverage to gate payment on verification, and the buyer's relationship is with the seller.

**Destination charges.** The charge is created on the platform account and funds are transferred automatically to one connected account. The platform is the settlement merchant by default and bears disputes and refunds (it can reverse the transfer to recover from the seller, subject to the seller's balance). `on_behalf_of` shifts settlement-merchant status to the connected account for some purposes, but dispute liability still flows through the platform's relationship. Fit: single-seller jobs; still commits you to one seller before verification completes.

**Separate charges and transfers.** Platform charges the buyer; later, independently, transfers any amounts to one or more connected accounts. Platform is merchant of record, holds funds on its Stripe balance in the interval, bears disputes, can hold transfers until verification passes, can split among a primary provider and a verifier. This is the only model that supports "pay after PASS." Its cost is that you are unambiguously the party that sold the service.

**Platform merchant-of-record.** Buyer contracts with you; you set price, issue invoices, handle tax, refunds, disputes. Sellers are your subcontractors. This matches an outcome authority that *sells verified results*. It also matches the service-bureau phase exactly, which is why the transition from phase 1 to Connect is smooth under this model.

**Seller merchant-of-record.** Buyer contracts with the seller; you facilitate. Less liability, but you can't gate settlement on verification without a contractual escrow arrangement, and buyers can't rely on you for the outcome. Wrong fit.

**Recommendation once sellers exist:** platform MoR + separate charges and transfers + Express accounts for sellers (Stripe handles their KYC, tax forms, payouts) + transfers released on PASS with a delay for new sellers. You accept dispute liability in exchange for control. Note: with Express/Custom accounts the platform is liable for the connected account's negative balances — the delayed-transfer policy is what protects you.

**Does this make you a money transmitter?** The generally accepted position is that a platform selling services as merchant of record, with Stripe as the licensed processor, is receiving payment for its own sales and paying its own subcontractors, not transmitting money on behalf of others. That holds as long as (a) the buyer's obligation is to you, (b) you don't hold buyer funds beyond settlement of your own sales, and (c) you don't let buyers direct funds to arbitrary third parties. Get a one-hour opinion from a payments lawyer when Connect enters; until then there's nothing to opine on.

**Spending authorization vs stored value.** Your instinct is correct. The database should record *authority*, not *balance*:

- `customer.credit_limit`, `customer.monthly_cap`, `customer.per_batch_cap`, `customer.approval_threshold` — enforced by your policy filter before a batch runs.
- Payment method on file via Stripe SetupIntent; charge on delivery (or monthly usage invoice via Stripe Billing meters).
- No prepaid balances on your books. If a customer insists on prepaying, issue a Stripe invoice for a deposit against future service, non-transferable, applied to their own invoices only. That's a customer prepayment for services, not stored value, but confirm with counsel if deposits get large.
- Never a wallet, never credits redeemable toward third parties, never a balance a buyer can move.

Working-capital exposure under this design = one billing cycle of upstream cost per customer, capped by their credit limit. Acceptable.

## 4. Verification redesigned around evidence diversity

Your invoice example is exactly the failure. Two engines sharing an OCR backbone misread a "3" as an "8" the same way; majority voting launders a correlated error into a "verified" value. **Consensus is a disagreement detector, not a truth oracle.** Agreement across engines with known-independent lineage lowers risk; disagreement escalates; a vote never settles a money field.

The architecture is an **evidence stack per field**, where each check is a (mostly) independent source of evidence, combined into a per-field risk score, with escalation to the next-more-expensive check only when risk stays above a field-type threshold.

**Tier 0 — free, deterministic (always run)**
- Schema and type validity; value parses from `source_text` (catches "$18,381.16" → 18331.16 transcription-to-number errors immediately, because the source text and the value must agree).
- Format rules: dates real and ordered, SCAC/DOT/ZIP/tax-ID formats, currency precision.

**Tier 1 — reconciliation (free, very high value)**
- Intra-document arithmetic: line items sum to subtotal; subtotal + tax + freight = total; quantity × unit price = extended; weights × counts consistent. A total off by $50 with a correct line-item sum fails here without any second engine.
- Cross-document: invoice vs PO vs delivery ticket/BOL — the accounting three-way match. If the customer supplies the counterpart documents, this is the strongest evidence available and costs nothing.
- Business rules against customer master data: vendor exists, PO number open, part number in catalog, carrier known, rate within contract.

**Tier 2 — provenance checks (cheap)**
- Does the claimed bounding box lie on the claimed page and contain text matching `source_text` (string similarity against a reference OCR layer)?
- Independent re-read of the crop only, by an engine of different lineage, compared to `source_text`. A crop is 1–2% of a page's tokens.

**Tier 3 — independent consensus (moderate)**
- Full-field agreement across engines *with a lineage graph*. Maintain a provider-lineage table (backbone OCR engine, model family, known shared components) and estimate correlation empirically from historical disagreement patterns (two engines that agree on 99.9% of errors are not independent regardless of what they claim). Weight agreement by estimated independence.

**Tier 4 — canaries and gold sets (fixed cost, unannounced)**
- Hidden canary documents with known answers injected into real batches at 1–3%. Fails caught here are provider-level signals, not just field-level.
- Buyer-supplied gold sets where available.

**Tier 5 — human audit (expensive, targeted)**
- Only fields whose risk remains above threshold after Tiers 0–3, weighted by field value (money and identifiers before descriptions). With provenance, a human verifies a crop in ~2–4 seconds rather than scanning a page: roughly $0.005–0.02 per field vs $0.50+ per page.
- Plus a small random audit of *passed* fields (0.5–1%) to measure false-accept rate — without this you cannot report FAR honestly.

**Combining evidence:** start with a simple per-field risk score = weighted sum of failed/passed checks, thresholds set per field class (money/ID fields strict, free-text lenient). Move to a calibrated model (logistic on check outcomes + document features) once you have a few thousand human-adjudicated fields. Escalation order is by cost: run everything free, then crops, then consensus, then humans.

**Your example under this stack:** Tier 0 passes (all three parse). Tier 1 fails if line items sum to 18,381.16 — caught with zero extra engines. If no line items exist, Tier 2 re-reads the crop with a different-lineage engine; Tier 3 records a disagreement (A vs B/C) on a money field → mandatory escalation to human, never a vote. Cost of catching it: one crop read plus one 3-second human look.

## 5. Provenance-first output: yes, and it's a build item

Provenance-first schemas materially improve both economics and trust, for four reasons:

1. **Verification becomes local.** Every check in §4 Tiers 0–2 operates on a value + crop pair, not a page. Verification cost drops from O(pages) to O(fields you care about).
2. **It converts hallucination into a detectable class.** An LLM extractor that invents a plausible value must also invent a plausible source and location; the reference-layer grounding check fails it.
3. **It produces the failure taxonomy for free.** Wrong-value-right-location (misread), right-value-wrong-location (lucky guess), no-location (hallucinated or derived), missing-field-that-exists (recall failure). These are the labels your context model trains on.
4. **It is the audit product.** A customer's auditor can click any number and see the pixels.

**Complications:**
- Not all providers emit value-level bounding boxes. Textract, Document AI, Azure DI, and some OCR-native vendors do; LLM-based extraction generally does not. Solution: the platform runs one cheap **reference OCR layer** per page (open-source or the cheapest cloud OCR, ~$0.001–0.002/page) with word-level boxes, and *grounds* every provider's `source_text` against it to assign or validate locations. This makes provenance universal regardless of provider, and it's yours.
- Fields with no single source: derived values (computed totals), inferred values (currency from context), absent fields. The schema needs `provenance.type ∈ {located, derived, inferred, absent}` with derivation rules for `derived` and explicit `absent` evidence (no match in reference layer).
- Multi-source fields (a total that appears on page 1 and page 3) — record all locations; disagreement between them is itself a check.

Make provenance mandatory in your output contract from day one, even with one provider. Call it the evidence schema; it's the thing customers will show their auditors and the thing competitors can't retrofit cheaply.

## 6. Two-stage experiment: agree, with three amendments

**Amendment 1 — the objective** (see the reframe at the top). Oracle = for each document, the provider minimizing API cost + expected human-review cost + expected error cost, with error cost set with the customer (a wrong invoice total costs more than a wrong description).

**Amendment 2 — add the cascade arm.** Compare five strategies, not two:
1. Best fixed provider.
2. Oracle (document-level).
3. **Cascade:** cheapest provider first, escalate to the next on verification failure. No prediction; verification *is* the router.
4. Predicted routing from cheap pre-features (your Experiment B).
5. Predicted + cascade.

If (3) captures most of the oracle's value, Experiment B is moot: you don't need to predict failures, only detect them cheaply. That's a better business (no classifier to maintain) and I'd bet on it for the first year.

**Amendment 3 — granularity and power.** A document-level oracle is a routing business. A *field-level* oracle (best provider per field) is an ensemble business — run several providers, pick per field. It has a higher ceiling and higher cost; measure it as a sixth arm, because with provenance-based field verification it may be the actual product.

Power: 150 gold pages × 10–30 fields ≈ 1,500–4,500 field observations. Enough to detect 2–3-point accuracy differences at the document-class level for 3–4 classes; not enough for fine context cells. Stratify the 500 pages deliberately toward ugly classes (handwriting, phone photos, rotated, low-res) — don't sample proportionally or the clean digital PDFs will swamp the signal. Double-annotate the gold set and report inter-annotator agreement; if humans agree on <97% of fields, that's your accuracy ceiling and the providers' "errors" partly aren't.

## 7. Verification economics, measured

Metrics to compute in the experiment, all at field level and rolled up to batch:

- **FAR** = P(field marked PASS | field wrong), by field class. Requires random audit of passed fields.
- **FRR** = P(field flagged | field right). Each false reject costs one human look.
- **Coverage** = fraction of fields that received a non-Tier-0 check.
- **Verification cost / 1,000 fields**, split by tier.
- **Verification latency** (P50/P95) per batch.
- **Human-touch rate** = fields sent to Tier 5 / total fields. This is the number the customer feels.
- **Error cost avoided** = errors caught × customer-assigned error cost.
- **Failover cost avoided** = batches that would have failed on the fixed provider but passed on cascade × rework cost.
- **False-reject cost** = FRR × fields × human cost per field.

Customer value equation, per 1,000 pages:

> (current human cost − our human-touch cost) + error cost avoided + audit value − our price ≥ 3 × our margin

Audit value is real but unquantified; price it at zero in the test and treat it as upside.

The MVP is therefore not "route a job." It is "produce a per-batch verification report with these nine numbers, for a paying customer, and show the equation is positive." That report *is* the product demo.

## 8. Vertical comparison

Scored 1–5 (5 best) on your ten criteria for a solo founder with your reach.

| Criterion | Freight / logistics (BOL, freight invoice, POD) | Construction / trades (material & delivery tickets, invoices, timecards) | Mining-services contractors (Elko: tickets, invoices, safety/compliance docs) | County records / title (Nevada, Idaho) | Generic AP (any SMB) |
|---|---|---|---|---|---|
| 1. Accessibility for you | 3 | 5 (Ben, Elko trades network) | 4 (Elko is a gold-mining hub; contractors everywhere) | 3 | 3 |
| 2. Existing OCR/extraction spend | 5 (freight audit is a mature industry) | 2 (mostly manual) | 2 | 3 | 5 (crowded) |
| 3. Cost of human processing | 4 | 5 (office manager keying tickets) | 5 | 4 | 4 |
| 4. Error cost | 5 (overbilling, detention, claims) | 4 (job-costing errors, billing disputes) | 4 (compliance, cost recovery) | 5 | 3 |
| 5. Provider quality variance | 4 (ugly, varied formats) | 5 (handwritten, greasy, photographed) | 5 | 3 (old but consistent) | 2 (clean invoices; everyone's good) |
| 6. Verification difficulty (lower = better) | 4 (three-way match native: BOL↔invoice↔POD) | 4 (ticket↔invoice↔PO match) | 4 | 2 (no counterpart docs) | 4 |
| 7. Regulatory burden (lower = better) | 4 | 5 | 4 (MSHA docs, but not PII-heavy) | 3 | 4 |
| 8. Batch sizes | 5 | 3 | 3 | 5 | 3 |
| 9. Sales cycle | 3 (brokers/3PLs move fast; shippers slow) | 4 (short, small budgets) | 3 (procurement gates for big miners; fast for contractors) | 2 | 3 |
| 10. Getting real documents | 3 | 5 | 4 | 3 | 3 |
| **Total** | **40** | **42** | **38** | **33** | **34** |

**Read the table honestly:**
- **Construction/trades** wins on the criteria that matter *during the experiment*: you can get ugly documents this week from people who trust you, variance is maximal, regulation is nil. It loses on batch size and budget: a sub's office manager keys 300 tickets a month, not 8,000. It may be a great place to prove the thesis and a poor place to scale.
- **Freight/logistics** wins on scale, existing spend, and native three-way match, and loses on your access and on incumbents (freight audit & pay firms and freight-document AI vendors exist). It's the better second market.
- **Mining-services contractors** is a real, local, underserved sub-niche with bigger volumes than general trades. Worth two phone calls.

**Recommendation:** run the experiment on construction/mining-contractor tickets and invoices because document access dominates everything at this stage, and simultaneously get one freight broker to give you 200 BOL/invoice pairs. Let the data choose the scaling vertical. Do not pick generic AP; you'd be the fortieth entrant with clean documents where routing has nothing to do.

## 9. No guarantees; insurance as a separate future

Agreed. "We're on the hook" was wrong. Correct language:

> Verified extraction with published QA methodology. Accuracy is measured per batch under that methodology and reported with confidence intervals. Measurements are not a warranty.

Contractually: disclaim warranty of accuracy, warrant only that the methodology was applied as documented, cap liability at fees paid. Customers who need a guarantee can buy one later from someone whose business is pricing risk.

**Insurance as a future product, analyzed separately.** AI-performance insurance already exists in early form (Munich Re's aiSure and Armilla underwrite model-performance guarantees, for example). What an underwriter needs and doesn't have: base error rates by provider × context, drift behavior over time, tail-error distributions on money fields, and correlation across providers (which determines whether a portfolio of AI-work risk is diversifiable). Your ledger, if honestly built, is that actuarial table. The product would be data licensing or a co-developed parametric policy ("if measured field-error rate on money fields exceeds X% on an audited sample, pay Y"), with you as the independent claims-measurement authority. Timing: 18–36 months after the ledger has thousands of audited batches. Guardrail: never underwrite yourself; the moment you carry the risk you have an incentive to shade the measurement.

## 10. Outcome authority vs marketplace

Is being the trusted issuer of performance attestations more defensible than owning the marketplace? Yes, on three grounds and with two cautions.

**Why more defensible:**
- Marketplaces are copied by anyone with distribution; authorities are copied by no one until they've earned trust over time, and trust accrues to the earliest neutral party (S&P, UL, FICO were each first).
- Neutrality is an asset marketplaces structurally lack (they sell placement); an authority's revenue can be designed not to depend on who wins.
- Attestations are portable, so sellers want them, which solves the supply side without exposure fees.

**Cautions:**
- **Issuer-pays corrupts.** Rating agencies paid by issuers gave us 2008. If sellers pay for certification, the fee must be flat, methodology-fixed, and results published regardless of outcome (UL's model), never linked to score.
- **Attestations carry liability.** A published "Provider X: 91.2% on handwriting" invites negligent-misrepresentation claims from X and reliance claims from buyers. Mitigate with public methodology, seller consent to be measured, evidence retention, and confidence intervals on every number. Never publish an unaudited number as an attestation.
- **You cannot start as an authority.** Authority requires volume; volume requires a product people buy. The service (verified extraction) is the on-ramp; the authority is the exit state. Sequence: sell results → accumulate audited outcomes → publish methodology → issue attestations to providers who consent → become the reference other platforms (including Stripe-gated settlement, Visa's directory, cloud marketplaces) point to.

Structurally the company becomes a **measurement company that happens to also fulfill orders**, not a marketplace that happens to measure.

## 11. Modeling context without a combinatorial database

Don't store cells. Store **events with feature vectors** and fit a model.

- **Event:** (provider, provider_epoch, field_class, document_features, check_outcomes, adjudicated_correct ∈ {0,1,unknown}, timestamp, cost, latency).
- **Document features** as continuous scores, not categorical bins: blur/contrast metric, skew angle, estimated handwriting fraction (from a small classifier on the reference OCR layer), table density, resolution, page count, language ID, document class (from a cheap classifier), field-type mix. Continuous features let the model interpolate; bins create the combinatorial problem.
- **Model, phase 1 (≤ ~10K documents):** hierarchical Beta-Binomial. Each (provider × doc-class × field-class) cell has a pass-rate posterior; its prior is the parent (provider × doc-class), whose prior is (provider). Sparse cells shrink toward parents automatically; you always have an estimate with an honest interval. This is a few hundred lines of code.
- **Model, phase 2 (> ~10K documents):** a gradient-boosted classifier per provider predicting P(field correct | features), trained on adjudicated outcomes, with isotonic calibration. The router needs *calibrated* probabilities more than accurate rankings, because it computes expected cost.
- **Routing decision:** for each candidate provider, expected cost = price + P(fail) × (retry + human-touch + error cost); pick the minimum; add an exploration term (Thompson sampling from the posterior) so you keep collecting data on non-favorite providers. Budget the exploration at 3–5% of volume.

The "graph" is then a fitted model plus its training log, not a table. Query it for any combination, including ones never seen; report the interval so callers know when it's guessing.

## 12. Decay and drift, practically

- **Effective sample size with decay.** Weight each event by e^(−age/τ) with τ ≈ 30–45 days for provider-level cells. Every estimate reports effective n, not raw n. "50 million jobs" becomes "effective n = 412,000 as of this week."
- **Epochs.** Capture provider-reported model/version identifiers whenever headers or metadata expose them. Where they don't, fingerprint behaviorally: a fixed canary set of 50–100 documents re-run per provider weekly (cost: trivial); compare field outputs to the previous run. Disagreement above a threshold opens a new epoch for that provider. Old-epoch evidence isn't discarded — it becomes the prior for the new epoch with sharply reduced weight (say ÷10), so the estimate moves fast but doesn't reset to ignorance.
- **Change-point detection on live traffic.** CUSUM or a Bayesian online change-point detector on rolling pass rate per provider × doc-class. Fires on silent degradation between canary runs.
- **Adaptive verification.** When an epoch opens or a change-point fires, raise that provider's Tier 3/5 sampling rate for the next N batches. This protects customers during the uncertain window and rebuilds evidence quickly — the two goals coincide.
- **Attestation hygiene.** Every published number carries: period, effective n, epoch identifier, confidence interval, and methodology version. A number with no epoch is a rumor.

## 13. Critique of the revised ordering

The ordering is right in spirit and has one trap and one hidden dependency.

**The trap:** "verification first" without a product that someone pays for is a research project. Verification and routing are not separable in practice; the cascade *is* routing, and the first customer buys "verified data with fewer human touches," which contains both. So step one is not "verification"; it is "sell verified extraction," which contains minimal verification, minimal routing (cascade across 3–4 upstream vendors), and produces the ledger as exhaust. The ledger then earns the right to the next steps.

**The hidden dependency:** verification quality depends on provider *diversity* from day one — you need 3–4 engines of different lineage to have independent evidence. So "independent provider network" (external sellers) is late in the order, but "multiple providers" is step zero. Don't let the sequence make you think you can start with one engine.

**A warning about the middle:** a service bureau's margins get squeezed as upstream vendors improve and cut prices. If the company is still "extraction reseller with QA" at month 18, it is a lifestyle business at best. The ledger must produce something beyond routing — attestations, drift alerts sold to providers, underwriting data — for the company to escape reseller economics. Build with that exit in mind; don't build it yet.

Revised order: **sell verified extraction (contains verification + cascade) → ledger → context model → predictive routing (if the experiment shows cascade isn't enough) → governance/policy views → attestations → external sellers → whatever agent commerce turns out to be.**

## 14. The standalone company

Assume no agent economy, no x402, no autonomous hiring. Is "independent verification + automatic provider selection for machine-generated business work" a company?

**Market:** intelligent document processing is a multi-billion-dollar category with established vendors (ABBYY, Hyperscience, Rossum, Klippa, Nanonets, and newer LLM-native players like Reducto, Extend, LlamaIndex's parsing products) plus AP-automation platforms. The category is not empty; it is full of single-engine vendors each reporting their own confidence scores. The gap is *neutral, multi-engine, evidence-backed, measured* output for buyers who can't or won't evaluate vendors themselves.

**Business shape:** usage-priced B2B, $0.10–0.40 per page depending on verification tier, gross margin 55–75% (COGS = upstream engines + reference OCR + verification compute + human sampling). ACV $5–60K for SMB and mid-market; higher for compliance-driven buyers. Sales-led beyond the first dozen customers.

**How big:** a solo founder with contractors can plausibly reach $0.5–2M ARR in a vertical or two; $10–20M ARR requires a sales team and multiple verticals; beyond that requires the attestation/insurance layer or a platform partnership (being the verification webhook behind someone else's settlement). Not venture-scale on its own; very much a real bootstrapped company with a strategic exit path (extraction vendors, AP platforms, or a cloud marketplace would buy a neutral verification layer).

**The key asymmetry:** if provider convergence kills routing (one engine at 99.5% everywhere), verification survives, because somebody independent still has to *measure* the 99.5% for the auditor. If verification turns out to be unbuildable at acceptable FAR, routing alone is a config table and the company dies. So the standalone company is a verification company. It is viable by itself. It is not a rocket by itself.

## 15. Competition under the narrower architecture

| Player | Move into transaction-level third-party verification? | Neutral? | Has tech? | Has the data? |
|---|---|---|---|---|
| Stripe | No. Would gate payouts on a verification webhook; wants a partner, not to be one. | Yes | Partial | No |
| OpenRouter | Adds LLM evals maybe; no document-extraction supply or human QA. | Yes for LLMs | Partial | LLM-only, unverified |
| Cloudflare | Could add outcome hooks to AI Gateway. Low interest in OCR. | Yes | Yes | No |
| Google / AWS / Microsoft | No — each sells an engine and reports its own confidence. Structurally non-neutral; won't route to rivals. | **No** | Yes | Own engine only |
| Scale AI | Most capable copier: human workforce, eval expertise, enterprise relationships. Neutrality damaged by Meta's stake; focused on large accounts. | Weak | Yes | No cross-provider ledger |
| Braintrust / Patronus / Galileo / Arize | Closest in methodology; they help buyers evaluate their *own* pipelines. Each customer's data is siloed by contract — they cannot build a cross-customer graph without consent they don't have. Could ship "vendor bake-off" features. | Yes | Yes | Siloed |
| Extraction vendors (Hyperscience, Rossum, Reducto, etc.) | They'll add "verification" of their own output. Non-neutral by construction. | **No** | Yes | Own engine only |
| Benchmark publishers | Could add document benchmarks; no money on the line, no transaction data. | Yes | Partial | Synthetic only |
| BPOs (Genpact, TaskUs, Sutherland) | They *already do this manually* for enterprises. Could productize "AI vendor QA." Slow, services DNA, but they own real error data. Better as your human-sampling partner than your competitor. | Mostly | No | Yes, unstructured |
| Vertical incumbents (freight audit firms; AP platforms like Bill.com, Ramp) | If you enter their vertical, they add AI-extraction QA as a feature. | No | Partial | Vertical-specific |

**Most likely to move first:** eval companies (adjacent, same buyers, same methodology) and Scale (capability). **Most incentivized not to be neutral:** cloud engines and extraction vendors — which is why buyers won't trust their self-reported confidence and why the slot exists. **Can copy the tech, lack the data:** everyone; the tech is not hard. **Owns necessary data today:** nobody owns cross-provider, money-on-the-line, adjudicated outcomes. BPOs come closest and can't use what they have.

## 16. GO / PIVOT / KILL

Run after the experiment below. All thresholds are on the reframed objective.

**Setup:** 500 pages stratified toward ugly classes; ≥4 providers of ≥3 distinct lineages; 150 pages double-annotated gold with inter-annotator field agreement ≥ 97%; error costs assigned per field class with the customer; provenance schema enforced for all providers via the reference layer.

| Test | Threshold | Fail means |
|---|---|---|
| **T1 Provider variance** | Best-vs-worst field accuracy gap ≥ 3 points overall, **and** rank reversal (a different best provider) on ≥ 2 document sub-classes that together are ≥ 20% of volume, each with a ≥ 4-point gap | No routing value; provider choice is a one-time config |
| **T2 Oracle advantage** | Oracle reduces total cost (API + human-touch + error cost) by ≥ 25% vs the best fixed provider at equal or better accuracy | Routing ceiling too low to fund a fee |
| **T3 Capturable advantage** | Cascade, or cheap-feature router, or their combination captures ≥ 50% of T2's savings | Routing value exists but isn't reachable cheaply |
| **T4 Verification FAR** | On money/ID fields: FAR ≤ 2% with 95% CI upper bound ≤ 5%; other fields ≤ 10% | Verification can't be trusted; no ledger |
| **T5 Verification FRR** | ≤ 5% on money/ID fields; ≤ 8% overall | Too many false alarms; human-touch savings evaporate |
| **T6 Verification cost** | ≤ 20% of target customer price per page and ≤ $0.03/page at T4's FAR | Verification eats the margin |
| **T7 Customer value** | (customer's current per-page human cost − our human-touch cost per page + error cost avoided) ≥ 3 × our target price | Not enough surplus to sell |
| **T8 Willingness to pay** | ≥ 3 of 8 qualified prospects sign a paid pilot (≥ $500) within 30 days of seeing results on *their own* documents; ≥ 1 commits recurring monthly volume | Nobody buys it regardless of the math |
| **T9 Ground-truth economics** | Ongoing human adjudication cost ≤ $2/page using crop-level review | Ledger can't grow affordably |

**Decision:**
- **GO:** T4, T5, T6, T7, T8, T9 pass **and** (T1 ∧ T2 ∧ T3) pass. Build verified extraction with routing.
- **PIVOT A — verification-only:** T4–T9 pass but T1/T2/T3 fail. Routing has no value; sell evidence-backed extraction on one engine with independent QA and audit. Still a company; smaller. Re-test routing every six months as providers change.
- **PIVOT B — ensemble product:** T1/T2 pass, T3 fails, and the field-level ensemble arm beats everything on T7. You run multiple engines per document and pick per field; cost is higher, human touches are lowest. Different COGS, same ledger.
- **PIVOT C — benchmark/report business:** T1/T2 pass, T4 fails. You can't verify at scale but can measure in the lab; sell periodic provider benchmarks by document class to buyers. Small, consulting-shaped, useful as a stepping stone only.
- **KILL:** T8 fails regardless of everything else. Or T4 and T1 both fail (nothing to verify and nothing to route). Or T7 fails by more than 2× (customers' current process is already cheap enough).

Don't negotiate the thresholds after seeing the data.

---

## Attack on the narrowed thesis

> "Different providers fail in predictable, context-specific ways, and a neutral system can cheaply predict those failures, verify outcomes, and therefore buy machine work more efficiently than a customer using one fixed provider."

Seven ways it could be false:

1. **Predictable at class level only.** Failures may be predictable by document class (handwriting → B) but not per document. Class-level routing is a five-row config table the customer writes once; no company. T1's rank-reversal condition tests exactly this, but be honest that "predictable" and "monetizable" aren't the same.
2. **Convergence.** Frontier multimodal models are closing the gap fast. If one provider hits 99.5% on ugly documents at $0.005/page within 18 months, routing value → 0. Verification survives as audit; routing dies. Plan the company so that outcome is survivable (§14).
3. **Correlated verification.** If verifiers share lineage with extractors, FAR has a floor you can't see. The evidence-stack design mitigates; only the random audit of passed fields measures it. If T4's CI won't close, the thesis's "verify outcomes" clause fails in practice.
4. **Not actually cheaper.** Customers already spot-check. Two passes plus your fee may cost more than their one pass plus a 5% spot-check, *unless* your human-touch rate is materially lower than theirs at equal error rate. T7 is the test, and it is the one most likely to fail on clean-document customers.
5. **Data-sharing refusal.** The graph requires cross-customer outcome telemetry (features + check outcomes, never content). If customers strike that clause, the ledger is per-customer and the moat is per-customer. Put anonymized-outcome telemetry in the standard terms from the first contract.
6. **Ground truth is the bottleneck.** The ledger is only as honest as adjudicated outcomes, and adjudication is human labor. Provenance shrinks it; it doesn't remove it. If T9 fails, the graph grows at the speed of your labeling budget.
7. **Cells stay sparse for years.** At SMB volumes you'll have confident estimates for a handful of provider × class cells, not hundreds. The hierarchical model gives you intervals, not certainty. The "performance graph" will be small and honest for a long time; sell it as such.

If 2 and 4 both bite, the company is a verification vendor with thin margins in a converging market. That is the realistic bear case and it is not fatal — it's a smaller company than the thesis implies.

---

## The cheapest experiment that tests the thesis

**Experiment 0 — half a day, ~$40.** Take 50 of the ugliest pages you can get from one contact (tickets, invoices). Run them through four providers via their consoles or a 100-line script. Label 50 pages yourself against a 10-field schema. Compute per-provider field accuracy and see whether any provider is best on the handwriting pages and a different one best on the clean pages. If all four are within a point of each other on everything, skip to Experiment A only if you doubt the sample; otherwise the routing half of the thesis is dead on arrival and you test verification alone.

**Experiment A/B — three weeks, ~$600–1,000.**
- Documents: 500 pages from 2–3 sources (one trades/mining contractor, one freight broker), stratified so ≥ 50% are ugly classes.
- Providers: 4–5 across ≥ 3 lineages (e.g., Textract, Document AI or Azure DI, Mistral OCR or an open-weights model, one LLM-based extractor). ~$50–150 in API calls.
- Reference layer: one cheap OCR pass with word boxes over all 500 pages; ground every provider's output to it. This is the only code you must write beyond scripts: the grounding + evidence-stack Tiers 0–2.
- Gold: 150 pages, double-annotated by two contractors at crop level using the provenance output (which is why it's cheap): ~$300–500. Measure inter-annotator agreement.
- Error costs: 30 minutes with each document source assigning $ to a wrong total, wrong ID, wrong description.
- Compute the six strategy arms, the nine verification metrics, and T1–T7.
- Customer test: show the 2–3 sources their own results as a one-page verification report (accuracy by field, fields flagged, cost, time). Ask for a paid pilot. Extend to 5 more prospects with the same report. That's T8.

Total: under $1,000 and about three weeks of your time, with no infrastructure beyond scripts, a spreadsheet, and a reference OCR pass. If it passes, the scripts become the first commit. If it fails, you learned the most important fact about the company for the price of a nice dinner.
