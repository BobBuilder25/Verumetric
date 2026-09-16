# VERUMETRIC — Claude Code Handoff

You are working in the `verumetric` repository with Tanner (GitHub: BobBuilder25, Fundamental Build LLC). This file is the complete orientation. Read it fully before touching anything. The three documents in `docs/critique/` are the full reasoning behind every decision here; consult them when a decision below seems arbitrary, but this file wins on conflicts.

---

## 1. What Verumetric is

Verumetric is a **machine-only verification and certification layer for machine-generated business work**, starting with structured document extraction.

The product, when it exists: a customer sends documents plus a JSON schema (plus counterpart documents and master data where available). Verumetric routes the extraction to one of several upstream providers, verifies every field claim with an automated evidence stack, and returns **evidence-backed structured data** split into a **certified stream** (auto-passed fields with a measured, published residual error rate) and an **exception stream** (FAIL / UNVERIFIED fields returned as null or low-confidence). No human at Verumetric touches a customer job. Humans only build ground truth and audit the verifier offline.

Long-term, the verified-outcome ledger becomes a performance graph (provider × capability × document context × epoch × time), which powers routing, provider attestations, and possibly underwriting data. **None of that is being built now.**

**We are not building right now:** a marketplace, an agent protocol, payments (Stripe Connect, x402, wallets, escrow), a seller SDK, predictive routing models, a dashboard, a control plane, or any platform infrastructure. We are running an experiment.

---

## 2. The thesis under test

> Different extraction providers fail in predictable, context-specific ways, and a fully automated evidence stack can certify a commercially useful fraction of important fields at a measurable residual error rate, without a human in the production path and without rerunning the whole job through an equally expensive model.

If this is false for our first document class, the company as conceived does not exist and we want to know that for under $1,000.

Key reframe (do not lose this): **API cost is a red herring.** Extraction costs $0.005–0.05/page; human data entry and review cost $0.50–2.00/page. The objective is minimizing **expected total cost = extraction cost + verification cost + retry cost + P(undetected error) × consequence of error**, which in practice means maximizing certified coverage at an acceptable residual error. Routing exists to serve that; cheaper API calls are a tiebreaker.

---

## 3. Hard constraints (non-negotiable)

1. **No human in the production path.** The simulated production pipeline must run start to finish autonomously. Humans create gold and score arms afterward. Any code path that "waits for review" is a bug.
2. **Verify the claim, not the job.** Verification inspects the evidence behind each field claim (crop, arithmetic, counterpart, master data). Whole-document reprocessing is a measured, budgeted tail event, not a strategy.
3. **Consensus is a disagreement detector, not a truth oracle.** Never majority-vote on a money or identifier field. Disagreement raises risk and triggers more evidence gathering.
4. **A field passes only on positive (confirming) evidence.** Type/format checks can reject; they cannot confirm. Reconciliation, counterpart match, master-data match, independent-lineage crop agreement, and premium-region reads confirm.
5. **Provenance is mandatory.** Every field value carries `{value, provenance{type, page, bbox, source_text}, field_class, consequence}`. Providers that don't emit locations get grounded against our reference OCR layer.
6. **Gold is created from page images + reference OCR only, never from provider output.** Otherwise gold inherits provider errors.
7. **Thresholds are pre-registered** (§7). They are committed to the repo before the first full run and are not renegotiated after seeing data.
8. **Scripts, not platform.** Everything in this phase is Python scripts plus flat files (JSONL/Parquet) and a notebook or two. No services, no queues, no auth, no UI. If you find yourself building infrastructure, stop and ask.
9. **Customer documents are confidential.** Keep all documents, crops, and outputs in `data/` (gitignored). Never commit a document, a crop, or a provider output containing document content. Never send documents to any provider not listed in `config/providers.yaml`.
10. **Log everything per field:** every check run, its result, its likelihood-ratio contribution, cost, latency, tier reached, and final decision. The analysis depends on this.

---

## 4. Domain vocabulary

- **Field claim:** one extracted value with provenance and a field class.
- **Field class:** `money`, `identifier` (PO, invoice #, routing #, SCAC, DOT, VIN), `quantity`, `date`, `party` (names/addresses), `text` (descriptions, memos), `line_item` (composite).
- **Important fields:** money, identifier, quantity, date, and anything the customer marks critical.
- **Consequence:** customer-assigned cost of an undetected error on that field (money fields default to their value × a multiplier; identifiers get a policy constant).
- **Lineage:** the underlying engine family of a provider. Two providers sharing a backbone are not independent. We maintain `config/lineages.yaml` and *estimate* independence empirically from gold errors.
- **Epoch:** a period during which a provider's behavior is stable; a new epoch opens when a canary set detects a behavior change. (Not needed for the experiment; the concept matters for logging.)
- **Reference layer:** one cheap word-box OCR pass per page that we own; used for grounding every provider's `source_text` and for structural checks (row counts).
- **Certified stream / exception stream:** auto-PASSED fields vs FAIL/UNVERIFIED fields.
- **STP rate:** straight-through-processing rate = share of important fields in the certified stream.
- **Residual error:** share of certified fields that are wrong per gold.
- **Coverage-vs-residual curve:** for each posterior threshold, the STP rate and residual error; the single most important output.

---

## 5. Evidence stack (implement exactly this shape)

Bayesian evidence accumulation per field with a stopping rule. Not a sequence of gates.

**Prior.** P(correct) from a simple table keyed by (provider, field_class, document_class); start with pessimistic defaults (e.g., 0.90) until gold calibrates it. Store in `config/priors.yaml`.

**Evidence items** (each contributes a likelihood ratio; initial LRs are hand-set in `config/evidence.yaml` and recalibrated from gold at the end):

- **Tier 0 — deterministic, free.**
  - Rejecting-only: type/format/range; date sanity; identifier checksums (ABA, IBAN, VIN where applicable); `value` must parse from `source_text` after normalization.
  - Confirming: arithmetic reconciliation (line items → subtotal; subtotal + tax + freight → total; qty × unit price → extended); cross-field consistency; duplicate detection; business rules against master data (`data/master/*.csv`: vendors, carriers, POs, parts, rate ranges); **counterpart-document match** (invoice ↔ PO ↔ BOL/POD/ticket).
- **Tier 1 — provenance grounding, near-free.** bbox on claimed page; `source_text` fuzzy-matches reference-layer words at that location; reference layer's own normalized read of the region agrees with `value`; multi-occurrence agreement across pages.
- **Tier 2 — independent crop reread, cheap.** A different-lineage engine reads only the crop (+ margin). Agreement confirms, weighted by estimated lineage independence. Disagreement raises risk; it does not decide.
- **Tier 3 — premium model on the disputed region.** Frontier multimodal model, region-scoped, given the candidate values and the reconciliation context. Never the whole packet by default.
- **Tier 4 — redundant region reprocessing.** Two or three additional engines on the region/page; combine with lineage-aware weighting from the empirical error-correlation matrix. Recall repair: if reconciliation fails for a missing line, use the reference layer's structural row detection to locate the skipped region and reprocess only that.

**Stopping rule.** After each check compute posterior P(wrong).
- PASS when `P(wrong) × consequence < cost(next cheapest check that could change the decision)`.
- FAIL/RETRY when P(wrong) exceeds the field class's retry threshold.
- UNVERIFIED when checks are exhausted or remaining checks are too correlated with evidence already gathered to be worth their cost.
- Customer policy maps UNVERIFIED → null / low-confidence / retry with another provider / reject batch.

**Cascade.** When a document accumulates FAIL/UNVERIFIED on critical fields beyond its provider's expected rate, resubmit the document (or failing regions) to the next provider in the cascade order. First-pass verification results are evidence for the second pass.

---

## 6. The experiment

**Goal:** produce coverage-vs-residual curves, escalation-depth histograms, cost/latency per tier, the lineage correlation matrix, calibration tables, and T1–T11 results for six arms on one document population. Budget ≤ $1,000, 3–4 weeks.

**Documents (target 500 pages, `data/raw/`).** Two sources: a trades/mining contractor (material/delivery tickets, supplier invoices, with POs or job-cost entries) and a freight broker (carrier invoices with BOLs/PODs/rate confirmations). Requirements: counterpart documents for ≥ 60% of pages; ≥ 50% "ugly" (handwriting, phone photos, rotation, low-res); ≥ 40% with totals/line items; ~10% deliberately without totals (to measure the recall problem). Tanner sources the documents; you build the intake and stratification report.

**Providers (`config/providers.yaml`, 4–5, ≥ 3 lineages).** One cloud OCR-native (Textract / Document AI / Azure DI), one LLM-native extractor (frontier multimodal model prompted to the schema), one specialist OCR (e.g., Mistral OCR), one open-weights engine we run ourselves (so one lineage is under our control). Premium verifier: a frontier multimodal model, region-scoped. Each provider gets an adapter that returns the common field-claim schema; adapters live in `src/verumetric/providers/`.

**Reference layer.** One cheap word-box OCR pass over every page → `data/reference/{doc_id}.json`.

**Gold (`data/gold/`, 150 pages, double-annotated).** Build a minimal annotation tool (a local HTML page or a CLI is fine) that shows the page image and reference-layer words and lets an annotator fill the schema. Never show provider output. Two annotators; adjudicate disagreements; report inter-annotator agreement per field class. Each document source assigns per-field-class consequences (recorded in `config/consequences.yaml`).

**Arms (all fully autonomous):**
1. Best fixed provider, verification on
2. Cheapest fixed provider, verification on
3. Machine-only cascade
4. Predictive routing from cheap page features (blur, skew, handwriting fraction, table density, document class) — simple model, trained with cross-validation on gold
5. Predictive routing + cascade
6. Oracle (per-document best provider computed from gold; the ceiling)
Informational: field-level ensemble (best engine per field).

**Outputs (`reports/`):** coverage-vs-residual per field class per arm (mark region below ~0.5% residual on money fields as extrapolated); escalation-depth histogram and share of whole pages reprocessed; cost per 1,000 fields by tier; verification cost per page; latency P50/P95; lineage error-correlation matrix (φ per pair); calibration table (predicted vs observed P(wrong) by decile); ambiguity floor; recall analysis on the no-totals subset; per-arm T1–T11; and a one-page STP report per document source in plain language for the customer conversation.

---

## 7. Pre-registered thresholds (commit as `THRESHOLDS.md` before the first full run)

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

**Pre-registered kill signals:** Tier 3 usage > 40% of important fields; money-field residual UB > 3% after cascade; ambiguity floor > 30%; 0 of 8 prospects accept the STP framing.

**Statistical honesty:** rule of three — zero errors in n audited passed fields gives a 95% UB of ~3/n. With ~300–600 gold money fields we can support "≤ ~1%," not 99.99%. Report every residual with its n and UB. Never print a residual without an interval.

---

## 8. Repository layout (create this)

```
verumetric/
  CLAUDE.md                  ← this file (or symlink HANDOFF.md → CLAUDE.md)
  THRESHOLDS.md              ← §7, committed before first full run
  docs/
    critique/                ← the three critique documents (background)
    adr/                     ← one ADR per non-obvious decision (ADR-0001 onward)
  config/
    providers.yaml           ← adapters, pricing, lineage id, region
    lineages.yaml
    priors.yaml
    evidence.yaml            ← initial likelihood ratios per check
    consequences.yaml
    schemas/                 ← extraction schemas per document class
  src/verumetric/
    schema.py                ← field-claim / provenance models (pydantic)
    reference.py             ← reference OCR layer + grounding
    providers/               ← one adapter per provider
    checks/                  ← tier0_deterministic.py, tier1_provenance.py, tier2_crop.py, tier3_premium.py, tier4_redundant.py
    evidence.py              ← posterior accumulation, stopping rule
    cascade.py
    routing/                 ← features.py, predictive.py (arm 4/5 only)
    arms.py                  ← runs the six arms
    scoring.py               ← gold comparison, curves, CIs, correlation, calibration
    costs.py                 ← per-call cost + latency ledger
  tools/
    annotate/                ← gold annotation tool (local, offline)
    stratify.py              ← intake + stratification report
  data/                      ← gitignored: raw/, reference/, gold/, runs/, master/
  reports/                   ← generated; commit only aggregate outputs, never document content
  tests/
```

`.gitignore` must exclude `data/` entirely and any file containing document content. Add a pre-commit check that fails on committing images/PDFs.

---

## 9. First tasks, in order

1. Create the repo layout, `.gitignore`, `pyproject.toml` (Python 3.11+, `uv` preferred), pre-commit content guard.
2. Write `THRESHOLDS.md` from §7 verbatim. Commit it first.
3. `schema.py`: the field-claim model with provenance types `{located, derived, inferred, absent}`.
4. `reference.py`: reference-layer OCR + grounding of `source_text` to word boxes (fuzzy match; return match score and matched bbox).
5. One provider adapter end to end (start with the open-weights engine or the LLM-native extractor — whichever Tanner has credentials for first), producing field claims in the common schema.
6. Tier 0 + Tier 1 checks with logging; run on 20 pages; produce a per-field evidence log.
7. `tools/stratify.py` and the intake report; `tools/annotate/` for gold.
8. Remaining adapters; Tier 2–4; `evidence.py` stopping rule; `cascade.py`.
9. `arms.py`, `scoring.py`, `reports/`.
10. Full run; write `reports/RESULTS.md` against `THRESHOLDS.md`; recommend GO / PIVOT (A–D) / KILL per the critique's decision table.

Ask Tanner for: provider credentials, the document drop, master-data CSVs, consequence values, and which two annotators to use. Do not guess credentials or invent sample documents; use synthetic placeholder pages only for unit tests and mark them as synthetic.

---

## 10. Working conventions

- **Output first, then iterate.** Don't ask clarifying questions before producing something when a reasonable default exists; state the assumption in the commit or ADR and proceed.
- **ADRs** for every non-obvious choice (which OCR for the reference layer, how LRs are initialized, cascade order, feature set for arm 4). Short: context, decision, consequences.
- **Multi-AI cross-check** is Tanner's standard practice; write code and reports so a second model can review them cold (clear docstrings, `reports/RESULTS.md` self-contained).
- **Costs:** every provider call goes through `costs.py`. Print a running spend total. Hard stop at $600 of API spend without Tanner's confirmation.
- **Secrets:** environment variables only, `.env` gitignored, `.env.example` committed.
- **Cloudflare:** not used in this phase. Local Python. Deployment questions are deferred until after a GO.
- **Don't build:** dashboards, APIs, queues, auth, payments, a marketplace, a seller SDK, learned routers beyond arm 4's simple model, anything for a second document class.

---

## 11. Reference: the critique documents

- `docs/critique/part-1.md` — landscape (what already exists: x402, AP2, Stripe MPP, Visa/Mastercard agent rails, OpenRouter, eval companies), economics, regulatory structure, why verification is the business.
- `docs/critique/part-2.md` — product vs defensible core, payment/legal architecture (service bureau first; Stripe Connect models for later), evidence-diversity verification, provenance-first schemas, vertical comparison (construction/mining contractors for the experiment; freight for scale), standalone-company analysis, competition, original GO/NO-GO.
- `docs/critique/part-3.md` — machine-only constraint, task-class taxonomy (YES/MAYBE/NO by verification asymmetry), the Bayesian evidence stack, audit design, statistical power limits, the revised thresholds in §7, the experiment spec in §6.

When in doubt: verify the claim, not the job; no humans in the path; pre-registered thresholds; scripts not platform; under $1,000.
