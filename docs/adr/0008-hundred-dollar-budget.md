# ADR-0008: A $100 budget, and how the experiment fits inside it

- **Status:** Accepted
- **Date:** 2026-09-16
- **Decided by:** Tanner
- **Amends:** CLAUDE.md §2, §6, §10 (was $1,000 budget / $600 hard stop)

## Context

The budget for this test is **$100**, not $1,000. The hard stop moves from $600
to $100 and is enforced in `costs.py` before every call, not reported after it.

The question this ADR answers is whether the experiment still answers the
question at a tenth of the budget, or whether it quietly becomes a different,
weaker experiment that cannot support its own conclusions.

## What $100 actually buys

Measured and estimated per-call costs, at posted rates:

| Item | Basis | Per page |
|---|---|---|
| LLM extraction, Sonnet-class | ~2,000 input + ~1,200 output tokens | ~$0.016 |
| LLM extraction, Opus-class | same tokens, higher rate | ~$0.040 |
| Reference layer (PaddleOCR, local) | ours | $0.000 |
| Tier 2 crop reread | ~400 input + ~50 output, region-scoped | ~$0.0013/call |
| Tier 3 premium region read | ~600 input + ~150 output, region-scoped | ~$0.007/call |
| Cloud OCR | varies by API: plain text detection to full form analysis | $0.0015–0.065 |

Two things fall out of this table, and they change the plan more than the budget
cut does:

**Verification is not the expensive part. Extraction is.** At roughly 12
important fields per receipt, Tier 2 firing on 15% of them and Tier 3 on 8%
costs about **$0.005 per page combined** — under a third of one Sonnet-class
extraction pass. The premium tiers are region-scoped by design (CLAUDE.md §5),
and region-scoping is what keeps them cheap enough to be worth having. This is
the first quantitative support for T5 being achievable, and it arrives before a
single page has been processed.

**The cloud OCR choice matters more than the cloud OCR vendor.** Plain text
detection and full form-and-table analysis differ by ~40× in price at the same
vendor. Confirm the specific API and its posted rate before enabling it in
`config/providers.yaml`; the pricing fields stay `null` until then.

## Decision

### 1. Extract once per page, per provider. Compute the arms from the cache.

The six arms differ in *which provider's output they select*, not in what was
extracted. So each provider reads each page once, the output is cached to
`data/runs/`, and every arm — including the oracle — is computed offline from
that cache. Cascade escalations and Tier 2/3 calls are cached per (page, field,
tier) the same way.

This is what makes six arms affordable at all. Re-running extraction per arm
would multiply the bill by six for no additional information, since the arms
would be reading identical pages with identical providers.

### 2. Sonnet-class as the bulk extractor; Opus-class as the premium verifier only

Cost is the occasion for this decision, but it is not the argument for it. The
thesis is that independent verification lets a buyer purchase *cheaper* machine
work safely. An experiment where the extractor is the most expensive model
available tests the least interesting version of that claim. Pairing a
cheaper bulk extractor with a premium region-scoped verifier is both the cheaper
design and the more on-thesis one: it asks whether cheap extraction plus
verification beats expensive extraction alone, which is the economic core of the
whole company.

It also slightly improves the lineage problem noted in ADR-0003 — extractor and
premium verifier are no longer the same model — though they remain the same
family, and the empirical correlation (T10) still governs how much Tier 3
evidence is allowed to count.

**Reversible:** if Tanner prefers the frontier model as the extractor, it is a
one-line change in `config/providers.yaml`, and running both is itself an
informative arm if budget remains.

### 3. Spend in three stages, with a decision point between each

| Stage | Scope | Ceiling | Purpose |
|---|---|---|---|
| **1 — pilot** | 50 pages, both runs (as-is + augmented), all providers, full ladder | **$10** | Replace every estimate above with a measurement. Produce the first evidence log and a real per-page cost. |
| **2 — main** | the remaining ~350 pages | **$60** | The measured run that T1–T11 are computed from. |
| **Reserve** | — | **$30** | Re-runs after a fix, the recalibration pass, and the mistakes that are not on this list because nobody has made them yet. |

Stage 2 does not start until Stage 1's measured per-page cost has been
multiplied out and shown to fit. If the pilot says the full run costs more than
$60, the page count comes down — not the reserve.

### 4. Prompt caching on the schema prefix

The extraction prompt (schema, instructions, output contract) is identical
across every page and is the larger part of each request's input. Caching that
prefix cuts input cost materially at no quality cost. Worth doing on day one,
because it is free savings and it is easiest to build in before there is a
working pipeline to retrofit.

## Consequences for statistical power — the part that matters

The budget cut costs **almost nothing in statistical power**, for a reason
specific to this corpus:

- Gold is the corpora's published annotations (ADR-0005), so gold costs $0. The
  budget buys API calls, not ground truth.
- Receipts are field-dense: a CORD page carries roughly 8 money fields and
  20–30 fields in total. At 400 pages that is **~3,200 money fields** and 8,000+
  fields overall.
- By the rule of three, "money-field residual ≤ 1% (95% UB)" needs ~300 audited
  passed money fields, and ≤ 0.5% needs ~600. Even a 100-page run clears the
  first; 400 pages clears the second comfortably.

So the pre-registered T2 thresholds (point ≤ 0.5%, 95% UB ≤ 1.5%) remain
testable at this budget. **No threshold is weakened, and none is renegotiated.**

What the budget does cost:

- **Fewer provider lineages.** T10 needs ≥ 3 lineages with pairwise error
  correlation φ < 0.3. PaddleOCR (ours, free) and one Claude-family extractor
  are two. The third must be the cloud OCR — which makes those credentials the
  binding constraint on T10, not the money.
- **Less room for re-running after a mistake.** Hence the $30 reserve and the
  staged gate, rather than one run at full scale.
- **No second extractor arm at frontier prices** unless the pilot comes in well
  under estimate.

## Consequences for operations

- `costs.py` defaults to a $100 limit and announces each quarter of the budget
  as it is crossed, so the spend is audible rather than discovered.
- `tools/budget.py` projects the full run from measured spend: at the current
  per-page cost, what will the remaining pages cost, and does it fit.
- Every estimate in this ADR is replaced by a measurement after Stage 1, and the
  ADR is updated with the real figures rather than left as a forecast nobody
  revisited.
