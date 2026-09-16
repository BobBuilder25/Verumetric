# ADR-0001: Construction/mining first, freight second, schema-driven throughout

- **Status:** Accepted
- **Date:** 2026-09-16
- **Decided by:** Tanner
- **Background:** `docs/critique/part-2.md` §8 (vertical comparison),
  `docs/critique/part-3.md` §2 (YES/MAYBE/NO), §9 (experiment spec)

## Context

The experiment needs one document population to build the harness around. part-2
§8 scored five candidates on ten criteria and the top two were close:
construction/trades at 42, freight/logistics at 40. They fail in opposite
directions.

**Construction/mining contractors** — material and delivery tickets, supplier
invoices, with POs or job-cost entries as counterparts. Maximum provider
variance (handwritten, greasy, photographed), negligible regulatory burden,
office-manager buyers rather than compliance officers — which part-3 §8 item 6
names as the mitigation for the one unconditional KILL, T8. Weaknesses: smaller
batches, thinner budgets, weaker reconciliation than freight.

**Freight** — carrier invoices with BOLs, PODs and rate confirmations. The
native three-way match is the strongest Tier 0 confirming evidence available,
volumes are larger, and freight audit is already a budgeted line item. Weakness:
Tanner's access is slower, and incumbents exist.

At this stage **document access dominates every other criterion**. An experiment
that cannot get real ugly paper measures nothing, whatever its scoring table
says. part-2 §8 reaches the same conclusion and recommends running on
construction/mining while simultaneously getting freight documents in hand.

## Decision

1. **Construction/mining-contractor documents are the first class**: material
   and delivery tickets and supplier invoices, with POs or job-cost entries as
   counterpart documents. The harness is built and validated against these.
2. **Freight is the second class and the eventual scaling market.** It is not
   built now, but it is never designed out.
3. **Everything is schema-driven per document class.** No document class is
   hardcoded anywhere: field lists, invariants, counterpart relationships,
   master-data bindings, priors, consequences and report groupings are all keyed
   by `document_class`. `config/schemas/` carries `construction/` and `freight/`
   from the first commit.
4. **Schemas are written against real paper**, not invented ahead of the
   document drop.

## Consequences

- Adding freight is a config change plus adapters' document-class handling, not
  a refactor. If that stops being true, it is a bug against this ADR.
- The experiment's reconciliation coverage depends on contractors supplying POs
  or job-cost entries. CLAUDE.md §6 requires counterpart documents for ≥ 60% of
  pages; construction is the harder class to hit that in. If it is missed, the
  measured ambiguity floor (T9) rises and PIVOT C — requiring reconciliation
  inputs as a condition of service — becomes the live branch. That is a real
  result, not a setup failure, but it must not be an accident: track counterpart
  coverage in the intake report and raise it before the full run, not after.
- Construction tickets are the harder population, so a GO here is stronger
  evidence than a GO on freight would have been, and a PIVOT D (this population
  is not machine-verifiable) does **not** condemn freight. Record the ambiguity
  floor per class so that distinction stays available.
- Batch sizes and budgets in construction are small. This decision optimizes for
  answering the thesis, not for the first revenue. Commercial scale is a freight
  question and stays deferred.
- Two annotators and one consequence-value session are needed per source. Both
  sources are in scope for gold, so budget accordingly.

## Alternatives rejected

- **Freight first** — better reconciliation and better economics, worse access.
  Slower to the answer, which is the only thing this phase buys.
- **Both, equally, from the start** — doubles adapter and schema work on a
  ≤ $1,000 budget and halves the pages per class, weakening every interval.
- **Generic AP** — part-2 §8 scored it 34: clean documents, no provider
  variance, forty prior entrants. Nothing to route and nothing to certify.
