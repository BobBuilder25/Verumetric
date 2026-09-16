# ADR-0005: Public real-document corpora, with contamination control

- **Status:** Accepted
- **Date:** 2026-09-16
- **Decided by:** Tanner
- **Numbering note:** requested as "ADR-0002", but that number is already taken
  (JSON-native claim values, committed earlier the same day). Filed as 0005 to
  keep ADR numbers stable once published.
- **Supersedes:** ADR-0001's experiment population (not its vertical choice);
  ADR-0003's counterpart plan, for the duration of this experiment.

## Context

There are no customer documents yet, and synthetic documents cannot test this
thesis. Generating a page means generating its ground truth, so every measured
residual would be a measurement of the generator, not of the providers. The one
thing the experiment exists to find out — whether real providers fail in
context-specific ways on real paper — is precisely what synthetic data cannot
tell us.

So the experiment runs on public corpora of real documents. Synthetic pages are
confined to unit tests, labeled synthetic, and **never enter an arm or a
T-metric**.

## Decision

### Corpora

| Role | Corpus | Size used | Why |
|---|---|---|---|
| **Primary (YES-class)** | **CORD** — Consolidated Receipt Dataset, NAVER CLOVA | ~400 pages: the test split plus part of train | Real photographed receipts with box-level annotations and ~30 entities including menu line items, subtotal, tax and total. Carries genuine intra-document arithmetic invariants (line items → subtotal → tax → total) *and* published provenance boxes — the two things the evidence stack needs. |
| **Secondary** | **SROIE** — ICDAR 2019 Task 3 | ~1,000 scanned receipts available; subset used | Second population for cross-population comparison. Weaker field coverage (company, date, address, total), so Tier 0 confirming evidence is thinner — useful precisely because it is thinner. |
| **No-totals subset** | **FUNSD** | ~50 pages | Noisy scanned forms with no arithmetic. Measures the recall problem where reconciliation cannot rescue us (part-3 §1: completeness is the check that cannot be made locally). |

### Licenses — verified 2026-09-16

- **CORD** — Creative Commons Attribution 4.0 International (CC BY 4.0), per the
  dataset's own repository. Permits commercial use with attribution. The public
  release is ~1,000 images (the full internal set was never released), which is
  why ~400 pages is a substantial fraction of it rather than a light sample.
- **FUNSD** — **non-commercial, research and educational use only**, per its
  published terms. Its images are a subset of RVL-CDIP and carry their own
  copyright, which the licensee is responsible for. Usable for this experiment;
  **not usable in any commercial claim, customer demo, or marketing artifact.**
- **SROIE** — **license not confirmed.** The ICDAR Robust Reading Competition
  site was unreachable (HTTP 503) at the time of writing, and no clear license
  statement was found elsewhere; the dataset is distributed through a
  registration-gated competition portal, and third-party GitHub mirrors do not
  carry the organizers' terms. **Treated as research-only and gated**: the
  download tool refuses to fetch SROIE and requires the archive be supplied
  locally with an explicit acknowledgment flag, so nobody acquires it absent a
  deliberate decision. Confirm terms with the organizers before use.

**Standing rule:** a research-only corpus is fine for finding out whether the
thesis holds. It is not fine as the evidence behind a commercial claim. Any
number in `reports/` derived from FUNSD (or SROIE, pending confirmation) is
labeled with its corpus, and must be reproduced on customer data before it
appears in front of a buyer.

No corpus images are committed. `data/` stays gitignored; `tools/download_corpora.py`
fetches, and the pre-commit guard blocks the rest.

### Contamination control

CORD and SROIE are almost certainly in the training data of the frontier models
we call. Memorization would inflate accuracy and suppress the provider
divergence that routing depends on — biasing us toward a **false PIVOT B** (no
routing value) and a **false GO** (residual looks better than it is). This is the
largest threat to the validity of the whole experiment, larger than any
threshold choice.

Every page is therefore run **twice**:

- **(a) as-is** — the contamination probe.
- **(b) augmented** — random rotation ±7°, Gaussian blur, JPEG quality 35–60,
  random crop/margin change, mild brightness and noise.

**All T-metrics are computed on the augmented run.** The as-is minus augmented
delta per provider is reported as the contamination estimate: a provider whose
accuracy collapses under mild augmentation was probably reciting rather than
reading. Augmentation is seeded and its config committed
(`config/augment.yaml`), so a run is reproducible page for page.

Two properties of the augmentation design that are not optional:

1. **Ground-truth boxes are transformed with the image.** The published
   annotations are box-level; rotating or cropping a page invalidates them. Each
   augmented page carries the exact affine used, and boxes are mapped through it.
   Skipping this would silently break every Tier 1 grounding measurement — the
   provenance check would be scored against coordinates for a page that no
   longer exists.
2. **The per-page seed is derived from (global seed, document id)**, not drawn
   from a single sequential stream. Adding a page later must not change the
   augmentation of every page after it.

### Gold

Published annotations are used as gold in place of hired annotators. They
contain known errors, so:

- Tanner adjudicates a **random 100-field slice** himself.
- The measured **annotation-error rate** is reported.
- **If it exceeds 2%, that rate is folded into every residual figure as gold
  noise and stated explicitly in `reports/RESULTS.md`.**
- **No residual is ever reported below the gold noise floor as if it were real.**
  A residual of 0.3% measured against gold that is 2% wrong is not a 0.3%
  residual; it is a number the instrument cannot resolve.

### Counterpart documents

Unavailable in these corpora, so cross-document reconciliation is untestable for
now. The matcher is built with a stubbed interface and a test; counterpart
evidence is marked **UNAVAILABLE** in every field's evidence log, never FAIL
(ADR-0003 made that distinction first-class for exactly this reason).

**`RESULTS.md` must state plainly that measured coverage is a LOWER BOUND.**
Real customer data adds the strongest confirming evidence in the stack — the
statement↔ticket and ticket↔invoice matches of ADR-0003 — and none of it is
present here. A coverage number from this run understates what the same stack
would achieve on paper that reconciles.

### Consequence values

Receipts are small-dollar, so the ADR-0003 defaults are scaled down: money =
value × 1.0 with a $5 floor; identifier $25; quantity $10; date $10; party $10;
text $2. Stand-ins, recorded as placeholders. T5's human-review clause stays
"pending customer input" and does not gate (THRESHOLDS Amendment 1).

## Consequences

- **T8 cannot be tested on public corpora** and is deferred to a customer step.
  It remains a hard KILL gate, so **a GO from this run is conditional on T8**.
  Recorded in THRESHOLDS Amendment 2.
- **T9's ambiguity floor is measured on receipts**, which likely carry a *higher*
  floor than construction tickets backed by supplier statements: small, dense,
  photographed, often single-source. Report it, flag the population difference,
  and do not read a T9 failure on receipts as a verdict on the construction
  vertical.
- The construction/mining vertical (ADR-0001) remains the commercial target. What
  changed is the experiment's population, not the market. When customer paper
  arrives, the same harness runs against it — which is the payoff of keeping
  everything schema-driven per document class.
- The reference layer matters more than before: with no counterpart documents and
  no master data, Tier 0's confirming evidence narrows to intra-document
  arithmetic, and Tier 1 grounding carries proportionally more weight.
- Every result from this run is a result about receipts. That is a real answer to
  "can a machine-only stack certify anything at a measurable residual," and it is
  not yet an answer about the vertical we intend to sell to.
