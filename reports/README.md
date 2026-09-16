# Reports

Generated output. Commit aggregate results only — curves, matrices, tables,
`RESULTS.md` — and never document content, crops, field values, or anything
traceable to a customer's paper. The pre-commit guard blocks the obvious cases;
it cannot read a table of extracted invoice totals and know what it is looking
at. That judgement is ours.

`RESULTS.md`, when it exists, must be self-contained enough for a second model
to review cold (CLAUDE.md §10), and every residual in it carries its n and its
upper bound. Never print a residual without an interval.
