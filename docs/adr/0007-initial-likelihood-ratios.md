# ADR-0007: Initial likelihood ratios, and damping for correlated evidence

- **Status:** Accepted
- **Date:** 2026-09-16
- **Implements:** CLAUDE.md §5 ("initial LRs are hand-set in config/evidence.yaml
  and recalibrated from gold at the end")

## Context

The evidence stack accumulates a posterior per field. Every check contributes a
likelihood ratio — P(observation | correct) / P(observation | wrong) — and the
stopping rule acts on the result. Before any gold exists, those ratios have to
come from somewhere, and where they come from decides how much evidence a field
needs before it is certified.

Two ways to get this wrong, and they are not symmetric:

- **Too timid** — fields escalate that did not need to, Tier 3 usage climbs, T3
  and T5 fail, and the experiment reports that verification is uneconomic when
  what it measured was a badly tuned prior.
- **Too confident** — fields certify on thin evidence, residual error hides in
  the certified stream, and T2 passes when it should not. **This is the failure
  that matters**: the first wastes money, the second produces a wrong answer
  about the whole thesis and is invisible until an audit catches it.

So the values start conservative and asymmetric, and the calibration test (T11)
is what tells us whether they were reasonable.

## Decision

### 1. Starting values, and their reasoning

The full table is `config/evidence.yaml`. The reasoning behind the load-bearing
ones:

- **`value_parses_from_source_text`, FAIL → 0.01.** Near-conclusive. The
  provider's own quoted text does not produce its own value; nothing else on the
  page is in dispute. This is the transcription error that no second engine
  would catch, because both engines read the pixels correctly and only the
  conversion went wrong.
- **`arithmetic_reconciliation`, PASS → 15, FAIL → 0.30.** Deliberately
  asymmetric. A misread total does not survive the sum of its own line items, so
  passing is strong. Failing is weak *about any particular field*: the invariant
  implicates a set, and says nothing about which member is wrong. Treating a
  failed invariant as strong evidence against one field would convict whichever
  field the loop happened to be examining.
- **`counterpart_match`, PASS → 40.** The strongest evidence available anywhere
  in the stack, and UNAVAILABLE on every public corpus. Its weight is recorded
  now precisely so the gap is visible: what this run measures without it is a
  lower bound.
- **Rejecting checks, PASS → 1.0, always.** Enforced in two places (the loader
  and `CheckResult`) so no future edit can quietly turn a format check into
  confirmation.

### 2. Correlated evidence is damped

Multiplying likelihood ratios assumes the observations are conditionally
independent. Several of ours plainly are not:

- `source_text_grounds` and `location_agrees` are computed from the *same*
  grounding call against the *same* reference layer.
- `type_format` and `value_parses_from_source_text` both fail on unparseable
  text.
- `master_data_match` and `counterpart_match` both depend on customer systems
  being right.

Multiplying them as independent manufactures confidence that does not exist, and
it does so **in the dangerous direction** — understating P(wrong), inflating the
certified stream, hiding residual error.

So each check declares a `group`. Within a group, the strongest likelihood ratio
counts in full and every other is raised to `correlation_damping` (0.3), which
keeps its direction while discounting its weight. A second correlated check
still moves the posterior; it just cannot pretend to be a second opinion.

0.3 is a judgement, not a measurement. The empirical correlation matrix (T10)
measures the real thing for cross-provider evidence; this damping covers the
within-tier case that T10 does not reach. If calibration (T11) comes back
over-confident, this exponent is the first dial to turn — before touching any
individual ratio, because a systematic bias points at the independence
assumption rather than at one check.

### 3. These numbers are provisional, and the repo says so

Every ratio is recalibrated from adjudicated gold at the end of the run.
`reports/RESULTS.md` reports both the hand-set and the recalibrated values, and
the T11 calibration table is the evidence for whether the starting point was
sane. A result computed with these numbers is a result about *this* weighting,
and that qualification belongs in the report.

## Consequences

- Fields carrying only rejecting evidence cannot certify, no matter how many
  checks pass. That is the intended behaviour and the direct implementation of
  CLAUDE.md §3 rule 4 — and on the public corpora it means fields with no
  arithmetic and no grounding will land in the exception stream rather than the
  certified one. Expected, and measured as coverage rather than hidden.
- Damping makes the stack escalate more than a naive multiplication would, which
  pushes on T3 (premium usage) and T5 (cost). If those fail while calibration
  shows the posterior well-calibrated, the honest reading is that verification
  on this population is expensive — not that the damping was wrong.
- Any change to these values after data exists must be reported as a
  recalibration, with both sets of numbers shown. Silently retuning ratios until
  the thresholds pass is the exact failure the pre-registration exists to
  prevent.
