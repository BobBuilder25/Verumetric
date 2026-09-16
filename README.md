# Verumetric

**Machine-only verification and certification for machine-generated business
work**, starting with structured document extraction.

A customer sends documents plus a JSON schema (plus counterpart documents and
master data where available). Verumetric routes extraction to an upstream
provider, verifies every field claim with an automated evidence stack, and
returns evidence-backed structured data split into a **certified stream**
(auto-passed fields with a measured, published residual error rate) and an
**exception stream** (FAIL / UNVERIFIED fields returned as null or
low-confidence).

No human at Verumetric touches a customer job. Humans build ground truth and
audit the verifier offline. That constraint is what makes the published numbers
describe the machine rather than the staff.

## Status

**Experiment, not product.** We are testing one thesis for under $1,000:

> Different extraction providers fail in predictable, context-specific ways, and
> a fully automated evidence stack can certify a commercially useful fraction of
> important fields at a measurable residual error rate, without a human in the
> production path and without rerunning the whole job through an equally
> expensive model.

If that is false for the first document class, the company as conceived does not
exist, and we want to know cheaply.

Nothing in this repo runs against a provider yet. No API spend has occurred.

## Read first

| File | What it is |
|---|---|
| [CLAUDE.md](CLAUDE.md) | The operative spec. Complete orientation; wins on conflicts. |
| [THRESHOLDS.md](THRESHOLDS.md) | Pre-registered T1–T11, kill signals, the rule-of-three limit. Committed before the first run and not renegotiated after seeing data. |
| [docs/critique/](docs/critique/) | The three critique documents — the reasoning behind every decision in CLAUDE.md. Background, not spec. |
| [docs/adr/](docs/adr/) | One ADR per non-obvious decision. |

## Layout

```
config/          providers, lineages, priors, evidence LRs, consequences, per-class schemas
src/verumetric/  schema, reference layer, provider adapters, tiered checks, evidence, cascade, arms, scoring, costs
tools/           stratification report, offline gold annotation tool
data/            gitignored entirely: raw/, reference/, gold/, runs/, master/
reports/         generated; aggregate outputs only, never document content
```

## Setup

```bash
uv sync                                  # Python 3.11+
git config core.hooksPath .githooks      # enable the document-content guard
cp .env.example .env                     # then fill in credentials
uv run pytest
```

### The document-content guard

`scripts/check_no_documents.py` refuses to commit document content — by path
prefix, by extension, and by sniffing the staged blob's magic bytes, so a PDF
renamed `notes.md` is still caught. Enable it with the `core.hooksPath` line
above, or through `.pre-commit-config.yaml` if you use the pre-commit framework.
Run it over everything already tracked with:

```bash
python3 scripts/check_no_documents.py --all
```

Customer paper is confidential and a commit is forever. If a file is genuinely
not document content, add a glob to `.documentguard-allow` with a comment saying
why — `--no-verify` disables the check for everyone and is not the escape hatch.

## What we are not building

No marketplace, no agent protocol, no payments, no seller SDK, no dashboard, no
control plane, no queues, no auth. Scripts and flat files. part-1 works through
why each of those layers is already owned by someone with more capital, and why
verification is the only unrented one.
