# Extraction schemas, per document class

One schema per document class, not one universal schema. part-1 §1: universal
job specs collapse to the lowest common denominator. Everything downstream —
checks, consequences, priors, scoring — is keyed by document class, so adding
the second class is a config change, not a refactor.

`construction/` is the first class and the one the harness is built around:
material and delivery tickets, supplier invoices, with POs or job-cost entries
as counterpart documents. `freight/` is second and the eventual scaling market:
carrier invoices with BOLs, PODs and rate confirmations. Both directories exist
from the start so neither is hardcoded (ADR-0001).

A class schema states:

- **`document_class`** — stable id, used as a key in priors, scoring and reports.
- **`fields`** — each with a name, a `field_class` from
  `{money, identifier, quantity, date, party, text, line_item}`, whether it is
  `important` (money, identifier, quantity, date, and anything the customer
  marks critical), and whether it is required.
- **`invariants`** — the arithmetic that must hold (line items → subtotal;
  subtotal + tax + freight → total; qty × unit price → extended). These are
  Tier 0's confirming evidence and the reason this class is verifiable at all.
- **`counterparts`** — which other document types reconcile against this one,
  and on which key (PO number, ticket number, load number).
- **`master_data`** — which `data/master/*.csv` tables a field is checked
  against (vendors, carriers, POs, parts, rate ranges).

Schemas are written against real paper. They are not being guessed at before the
document drop arrives — a schema invented from imagination would set the field
list, the invariants, and therefore the measured coverage, all without a single
real ticket to check it against.
