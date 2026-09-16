# Charter — what Verumetric is for

Confirmed by Tanner, 2026-09-16. This document exists because the repository
kept narrowing: a session reads a spec written tightly around documents,
concludes that documents are the point, and builds accordingly. Documents are
the first proof. They are not the point.

**Read this before CLAUDE.md.** CLAUDE.md is the build spec for the current
experiment. This is what the experiment is in service of.

---

## The task

> As more work gets done by machines, the bottleneck stops being *doing* the
> work and becomes *trusting* it. Verumetric is the layer that tells you whether
> machine-done work is actually right — with a measured number attached, for any
> task where correctness can be established from evidence.

## What a customer buys

Not extraction. Not AI. **The elimination of the checking step.**

Anyone who has a machine do real work has to check it, the checking costs more
than the work did, and it does not scale. So either they check everything and
the machine saved nothing, or they check nothing and eat unknown errors.

We return the work in two piles:

- **Certified** — right, with a measured residual error rate and an honest
  interval. No human touched it, at our end or theirs.
- **Exceptions** — could not be established. Look at these.

The product is that the first pile is trustworthy without a person and the
second pile is small. Their checking labour drops from 100% to the exception
rate.

## Why it has to be someone else

Every vendor grades its own homework, and every buyer knows it. A vendor's own
confidence score is marketing. The slot is for a party that does not sell the
work, has no stake in which engine wins, and publishes its method so the numbers
can be audited.

Nobody currently sells transaction-level, money-on-the-line verification of
machine work by a neutral third party. Benchmarks measure models in a lab. Eval
tools help a buyer check their own pipeline against their own data. Neither
certifies a specific job with a number you could hand an auditor.

## Three answers, settled

**1. Scope — documents first, general underneath.**
Customer-facing today: send your invoices and tickets, get checked data with a
measured error rate. Internally: nothing hardcodes "document." A task type is
its evidence sources — invariants, vocabularies, oracles — supplied as
configuration. Adding transcription, data cleanup, or code-with-tests must be
configuration, not a rewrite. See ADR-0009 for where this holds today and the
one place it does not yet.

**2. First buyer — businesses with back-office paper.**
Contractors, suppliers, freight brokers: anywhere an office manager keys
invoices and tickets today. Budgeted spend, repeat volume, and a cost that can
be pointed at. Individual and one-off jobs (a box of family recipes) are the
same machine and a worse business: low ticket, no repeat, and no auditor ever
asks for the error rate.

**3. Our role — we pick the engine and check the work.**
One job in, one bill, one party responsible. Grading-only (customer brings their
own output) stays available later, once the measurement is trusted — but running
the work is what accumulates the record that becomes the actual asset.

## What makes a task eligible

A task is verifiable to the degree its output leaves evidence that would have
failed had the work been wrong: invariants, closed vocabularies, external
oracles, locality, structural counts, recomputation, an independent re-read. The
full test is in [task-verifiability.md](task-verifiability.md).

That covers a great deal — invoices, tickets, recipes, timestamped
transcription, data transformations, code with tests someone else wrote. It does
not cover "is this essay good," for us or for anyone. That boundary is not
caution; it is where the thing being sold stops existing.

## Where it goes

Every certified job leaves a record: this engine, this kind of work, this
context, right or wrong. Nobody holds that data, because nobody has been
standing where money moves on the answer. It compounds into a performance graph
that cannot be downloaded, bought, or reconstructed from our documentation —
and the company becomes the party whose measurement others cite rather than a
vendor among vendors.

**None of that is being built now**, and building toward it prematurely is the
failure mode the critique documents were written to prevent.

## What the current experiment is

A **$100 test of whether the core claim is true at all**: can an automated
evidence stack certify a commercially useful share of fields at a measurable
error rate, with no human in the path, without re-running the job through an
equally expensive model?

Documents first because that is where evidence is densest. A failure there is
decisive — if the stack cannot certify work carrying invariants *and* oracles
*and* locality, it will not certify work with less. A failure on thin-evidence
work would be ambiguous, and ambiguity is what $100 cannot buy its way out of.

If the claim is false, there is no company, and the point is to know that for
$100 rather than $100,000.
