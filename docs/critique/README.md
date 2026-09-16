# Critique documents

Three documents, written September 15, 2026, loaded here verbatim as background
reasoning. They were written to disprove the idea, not to sell it.

`CLAUDE.md` at the repository root is the operative spec. These files explain
*why* its decisions are what they are; consult them when a decision looks
arbitrary. **CLAUDE.md wins on conflicts.**

**Among these three, later parts supersede earlier ones.** Each was written
after the founder pushed back on the previous one, so the disagreements are the
argument, not noise.

| Document | What it establishes |
|---|---|
| [part-1.md](part-1.md) — Skeptical Critique | Five of seven proposed layers are already built by better-capitalized companies. Only outcome verification and the performance record derived from it are unsolved. Everything else is rented. |
| [part-2.md](part-2.md) — Narrowed Thesis | API cost is a red herring; human-review cost is the prize. Consensus is a disagreement detector, not a truth oracle. Introduces the evidence stack, provenance-first output, the reference OCR layer, and the hierarchical context model. |
| [part-3.md](part-3.md) — Machine-Only Verification | Under the no-human-in-the-production-path constraint: verification asymmetry, the YES/MAYBE/NO task classes, the Bayesian evidence ladder with a consequence-weighted stopping rule, statistical power limits, and the T1–T11 thresholds. |

## Known supersessions

- **Payments.** part-1 §7–§10 designs marketplace settlement (Stripe Connect,
  prepaid balances, delayed payouts). part-2 §2–§3 replaces it: operate as an
  ordinary B2B service with upstream vendors under your own accounts. No
  Connect, no balances, no payouts, no money-transmission question until roughly
  ten external sellers exist.
- **Verification design.** part-1 §11's tiered consensus is replaced by part-2
  §4's evidence stack, which is in turn replaced by part-3 §3's Bayesian ladder
  with likelihood ratios and a stopping rule. Majority voting never decides a
  money field in any version after part-1.
- **Human sampling.** part-1 §4 and part-2 §4 Tier 5 put human review in the
  production path. part-3 removes it entirely: humans build gold and audit the
  verifier offline, never a customer's job.
- **GO/PIVOT/KILL.** part-2 §16's T1–T9 (human-in-loop) is superseded by part-3
  §6's T1–T11 (machine-only). The thresholds in force are pre-registered in
  [THRESHOLDS.md](../../THRESHOLDS.md).
- **Objective function.** part-1's "minimize API cost at ≥ X% accuracy" is wrong
  and part-2 corrects it at the top: minimize (API cost + human-review cost of
  flagged fields + expected cost of errors that pass).

## Editing policy

These files are a historical record, loaded byte-for-byte as delivered. Do not
rewrite them to match later thinking — record the disagreement in
`docs/decisions/` and add it to the supersession list above.
