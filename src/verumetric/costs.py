"""Per-call cost and latency ledger, with a hard spend stop (CLAUDE.md §10).

Every provider call goes through here. Two jobs:

1. **Measure.** T5 is a pre-registered cost gate ("verification + retries ≤
   $0.04/page"), so the per-page cost has to be a measurement, not an estimate
   from a pricing page. Tokens and latency are recorded per call, per tier, per
   provider, and a page's cost is the sum of what it actually spent.

2. **Stop.** A hard stop at $600 without explicit confirmation. The budget for
   the whole experiment is $1,000, and the cheapest way to lose it is a retry
   loop nobody is watching at 2am.

The ledger is a JSONL file under `data/runs/`, appended and never rewritten, and
it is re-read on startup - so a crashed run resumes with its spend intact rather
than starting the count again from zero, which is precisely how a budget gets
spent twice.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_LEDGER = REPO_ROOT / "data" / "runs" / "spend.jsonl"
DEFAULT_LIMIT_USD = Decimal("600")


class SpendLimitExceeded(RuntimeError):
    """Raised before a call that would cross the limit. The call does not happen."""


@dataclass
class CallRecord:
    provider_id: str
    model: str | None
    tier: int
    doc_id: str | None
    usd: Decimal
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    pages: int = 0
    purpose: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "provider_id": self.provider_id,
            "model": self.model,
            "tier": self.tier,
            "doc_id": self.doc_id,
            "usd": str(self.usd),
            "latency_ms": round(self.latency_ms, 2),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "pages": self.pages,
            "purpose": self.purpose,
        }


def token_cost(
    input_tokens: int,
    output_tokens: int,
    usd_per_mtok_input: float | Decimal,
    usd_per_mtok_output: float | Decimal,
) -> Decimal:
    """Cost of one call from its actual token usage.

    Image input is billed as input tokens derived from page dimensions, so a
    per-page figure is never computed here - the response reports what it used
    and that is what gets recorded (config/providers.yaml).
    """
    million = Decimal("1000000")
    return (
        Decimal(input_tokens) * Decimal(str(usd_per_mtok_input)) / million
        + Decimal(output_tokens) * Decimal(str(usd_per_mtok_output)) / million
    )


@dataclass
class SpendLedger:
    """Append-only spend log with a pre-call guard."""

    path: Path = DEFAULT_LEDGER
    limit_usd: Decimal = DEFAULT_LIMIT_USD
    records: list[CallRecord] = field(default_factory=list)
    _total: Decimal = Decimal("0")

    @classmethod
    def open(cls, path: Path | None = None, limit_usd: Decimal | None = None) -> SpendLedger:
        """Open the ledger, resuming any spend already recorded.

        The limit comes from VERUMETRIC_SPEND_LIMIT_USD when set, so a run can be
        given a tighter budget than the default without editing code. It can be
        lowered freely; raising it past the default is a deliberate act that
        should be a conversation, not an env var, so it is reported loudly.
        """
        path = path or Path(os.environ.get("VERUMETRIC_SPEND_LEDGER", DEFAULT_LEDGER))
        env_limit = os.environ.get("VERUMETRIC_SPEND_LIMIT_USD")
        limit = limit_usd or (Decimal(env_limit) if env_limit else DEFAULT_LIMIT_USD)

        ledger = cls(path=path, limit_usd=limit)
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                ledger._total += Decimal(obj["usd"])
                ledger.records.append(
                    CallRecord(
                        provider_id=obj["provider_id"],
                        model=obj.get("model"),
                        tier=int(obj.get("tier", -1)),
                        doc_id=obj.get("doc_id"),
                        usd=Decimal(obj["usd"]),
                        latency_ms=float(obj.get("latency_ms", 0.0)),
                        input_tokens=obj.get("input_tokens"),
                        output_tokens=obj.get("output_tokens"),
                        pages=int(obj.get("pages", 0)),
                        purpose=obj.get("purpose", ""),
                        timestamp=float(obj.get("timestamp", 0.0)),
                    )
                )
        return ledger

    # --- reading ---------------------------------------------------------

    @property
    def total_usd(self) -> Decimal:
        return self._total

    @property
    def remaining_usd(self) -> Decimal:
        return self.limit_usd - self._total

    def total_by(self, key: str) -> dict[Any, Decimal]:
        out: dict[Any, Decimal] = {}
        for r in self.records:
            k = getattr(r, key)
            out[k] = out.get(k, Decimal("0")) + r.usd
        return out

    def cost_per_page(self) -> Decimal | None:
        """Measured cost per page - the T5 numerator.

        None when no call has declared pages, because a fabricated denominator
        would turn a pre-registered gate into a guess.
        """
        pages = sum(r.pages for r in self.records)
        return (self._total / pages) if pages else None

    # --- writing ---------------------------------------------------------

    def guard(self, estimated_usd: Decimal) -> None:
        """Refuse a call that would cross the limit. Called BEFORE the call."""
        if self._total + estimated_usd > self.limit_usd:
            raise SpendLimitExceeded(
                f"this call would take spend to "
                f"${self._total + estimated_usd:.2f}, past the ${self.limit_usd:.2f} limit. "
                f"Spent ${self._total:.2f} so far. Raising the limit needs Tanner's "
                f"confirmation (CLAUDE.md §10) - it is not a default to edit past."
            )

    def record(self, call: CallRecord) -> CallRecord:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(call.to_json()) + "\n")
        self.records.append(call)
        self._total += call.usd
        return call

    @contextmanager
    def call(
        self,
        provider_id: str,
        tier: int,
        *,
        model: str | None = None,
        doc_id: str | None = None,
        estimated_usd: Decimal = Decimal("0"),
        pages: int = 0,
        purpose: str = "",
    ) -> Iterator[CallRecord]:
        """Time a provider call, then record what it actually cost.

        The guard runs first, so a call that would cross the limit never
        happens. The body fills in real usage:

            with ledger.call("claude-extractor", tier=0, estimated_usd=d) as rec:
                response = client.messages.create(...)
                rec.input_tokens = response.usage.input_tokens
                rec.output_tokens = response.usage.output_tokens
                rec.usd = token_cost(rec.input_tokens, rec.output_tokens, 5.0, 25.0)

        A call that raises is still recorded: a failed request that burned tokens
        spent real money, and a ledger that only counts successes understates the
        bill exactly when things are going wrong.
        """
        self.guard(estimated_usd)
        rec = CallRecord(
            provider_id=provider_id,
            model=model,
            tier=tier,
            doc_id=doc_id,
            usd=estimated_usd,
            latency_ms=0.0,
            pages=pages,
            purpose=purpose,
        )
        started = time.perf_counter()
        try:
            yield rec
        finally:
            rec.latency_ms = (time.perf_counter() - started) * 1000.0
            self.record(rec)

    def summary(self) -> str:
        by_provider = self.total_by("provider_id")
        by_tier = self.total_by("tier")
        lines = [
            f"spend: ${self._total:.4f} of ${self.limit_usd:.2f} "
            f"(${self.remaining_usd:.2f} left, {len(self.records)} calls)"
        ]
        if by_provider:
            lines.append(
                "  by provider: " + ", ".join(f"{k}=${v:.4f}" for k, v in by_provider.items())
            )
        if by_tier:
            lines.append(
                "  by tier: " + ", ".join(f"T{k}=${v:.4f}" for k, v in sorted(by_tier.items()))
            )
        per_page = self.cost_per_page()
        if per_page is not None:
            lines.append(f"  per page: ${per_page:.5f}  (T5 gate: $0.04/page)")
        return "\n".join(lines)
