# What makes a task verifiable

Verumetric checks machine work. The question that decides whether it can check
*your* task is not what the task is about — it is whether the work leaves
evidence behind that would have failed had the work been wrong.

That test is task-agnostic. It applies to an invoice, a recipe card, a
translation, a code change, a lab result. What varies is which kinds of evidence
exist, and how much of it the stakes justify buying.

## The test

A task is verifiable to the degree that its output carries:

| Evidence | The question it answers | Cost |
|---|---|---|
| **Invariants** | Does the output satisfy constraints it had to discover but we only have to evaluate? | free |
| **Closed vocabularies** | Is this value a member of a set most wrong readings fall outside? | free |
| **External oracles** | Does something outside the work agree — a counterpart document, a master table, a test suite? | one lookup |
| **Locality** | Does each claim point at a small piece of evidence we can inspect without redoing the work? | ~free |
| **Structural counts** | Does the output account for as many items as the input appears to contain? | free |
| **Recomputation** | Can the claim be re-derived from the output itself? | free |
| **Independent re-read** | Does a different engine, of different lineage, read the same thing? | cheap |

A task with none of these cannot be verified by anyone, at any price. Not by us,
not by a competitor, not by a human — "is this poem good" has no evidence that
would have failed had the poem been worse.

## Two things that are often confused

**Verifiability is a property of the work, not of the subject matter.** "Digitize
100 of grandma's recipes" and "process 100 supplier invoices" differ in which
evidence exists, not in whether the system applies:

| | Recipe card | Supplier invoice |
|---|---|---|
| Invariants | none — nothing sums | qty × price = extended; lines → subtotal → total |
| Closed vocabulary | strong — cooking units are a set of about eight | strong — vendor list, part numbers, carrier codes |
| External oracle | none per card | the supplier's monthly statement, the PO |
| Locality | yes | yes |
| Structural count | yes — ingredient lines are countable | yes — line items are countable |
| Independent re-read | yes | yes |

The recipe has four of six. That is a real ladder, not an empty one. It has less
confirming evidence than an invoice, so it certifies a smaller share of fields,
and the system reports that share rather than guessing past it.

**Required confidence is set by consequence, not by task type.** The stopping
rule buys evidence until the expected cost of being wrong falls below the price
of the next check. A wrong ingredient costs a disappointing dinner. A wrong
invoice total costs the invoice. So the same evidence that certifies the recipe
field keeps climbing on the invoice field — automatically, with no per-task
configuration. Two tests assert exactly this
(`test_the_same_evidence_escalates_when_the_stakes_are_higher`).

This is why low-stakes work is often *cheaper* to certify than high-stakes work,
which is the opposite of the usual intuition.

## What this means for scope

The system is **task-general and evidence-bounded**. Adding a task means
supplying its evidence sources — its invariants, its vocabularies, its oracles —
not rewriting the ladder. The checks are generic: the same code path that
validates "tablespoon" against cooking units validates a SCAC code against a
carrier list.

What the first experiment narrows is not the system's reach but the **order of
proof**. The first measurement should happen where evidence is densest, because
that is where a result means something unambiguous: if the stack cannot certify
work that has invariants *and* oracles *and* locality, it will not certify work
with fewer. A failure there is decisive. A failure on a recipe card would be
ambiguous — was it the stack, or a document that carries little evidence to
begin with?

Proving it on dense evidence first is a sequencing decision. It is not a claim
that the thin cases are out of scope.

## The honest output for a thin-evidence task

For a job like 100 recipe cards, the system's answer is not "yes" or "no". It is:

> Of 1,340 fields, 1,190 are certified with a measured residual error of X%
> (n, upper bound). 150 are returned as exceptions for you to glance at. Here is
> which checks were available, and which could not run.

That is a useful product for grandma's recipes. It is a *more* useful product
for an invoice, because more of the fields land in the certified stream. Both
are the same machine.
