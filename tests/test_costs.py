"""Tests for the spend ledger.

The budget for the whole experiment is $1,000 and the cheapest way to lose it is
an unattended retry loop. These tests are about the guard being load-bearing.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from verumetric.costs import CallRecord, SpendLedger, SpendLimitExceeded, token_cost


@pytest.fixture
def ledger(tmp_path):
    return SpendLedger.open(tmp_path / "spend.jsonl", Decimal("1.00"))


def test_token_cost_uses_actual_usage():
    """Image input is billed as tokens derived from page size, so per-page cost
    is measured from the response, never estimated from a pricing page."""
    assert token_cost(1_000_000, 0, 5.0, 25.0) == Decimal("5")
    assert token_cost(0, 1_000_000, 5.0, 25.0) == Decimal("25")
    assert token_cost(1500, 400, 5.0, 25.0) == Decimal("0.0175")


def test_recording_accumulates(ledger):
    ledger.record(CallRecord("p", "m", 0, "d1", Decimal("0.01"), 10.0, pages=1))
    ledger.record(CallRecord("p", "m", 1, "d1", Decimal("0.02"), 10.0))
    assert ledger.total_usd == Decimal("0.03")
    assert ledger.remaining_usd == Decimal("0.97")


def test_the_guard_refuses_a_call_that_would_cross_the_limit(ledger):
    ledger.record(CallRecord("p", "m", 0, None, Decimal("0.99"), 1.0))
    with pytest.raises(SpendLimitExceeded, match="past the"):
        ledger.guard(Decimal("0.02"))


def test_the_guard_runs_before_the_call_not_after(ledger, tmp_path):
    """A limit checked afterwards is a limit that has already been crossed."""
    ledger.record(CallRecord("p", "m", 0, None, Decimal("1.00"), 1.0))
    called = False
    with pytest.raises(SpendLimitExceeded):
        with ledger.call("p", tier=3, estimated_usd=Decimal("0.50")):
            called = True
    assert called is False


def test_spend_survives_a_restart(tmp_path):
    """A crashed run that resumed from zero would spend the budget twice."""
    path = tmp_path / "spend.jsonl"
    first = SpendLedger.open(path, Decimal("1.00"))
    first.record(CallRecord("p", "m", 0, None, Decimal("0.42"), 1.0))
    second = SpendLedger.open(path, Decimal("1.00"))
    assert second.total_usd == Decimal("0.42")
    assert len(second.records) == 1


def test_a_failed_call_is_still_recorded(ledger):
    """A request that raised after burning tokens spent real money; a ledger that
    counts only successes understates the bill exactly when things go wrong."""
    with pytest.raises(RuntimeError):
        with ledger.call("p", tier=2, estimated_usd=Decimal("0.01")) as rec:
            rec.usd = Decimal("0.01")
            raise RuntimeError("provider timed out")
    assert ledger.total_usd == Decimal("0.01")


def test_latency_is_measured(ledger):
    with ledger.call("p", tier=0, estimated_usd=Decimal("0")) as rec:
        rec.usd = Decimal("0")
    assert ledger.records[-1].latency_ms >= 0.0


def test_cost_per_page_is_none_without_pages(ledger):
    """A fabricated denominator would turn a pre-registered gate into a guess."""
    ledger.record(CallRecord("p", "m", 0, None, Decimal("0.10"), 1.0, pages=0))
    assert ledger.cost_per_page() is None


def test_cost_per_page_is_the_t5_numerator(ledger):
    ledger.record(CallRecord("p", "m", 0, "d1", Decimal("0.02"), 1.0, pages=1))
    ledger.record(CallRecord("p", "m", 1, "d2", Decimal("0.04"), 1.0, pages=1))
    assert ledger.cost_per_page() == Decimal("0.03")


def test_totals_split_by_provider_and_tier(ledger):
    ledger.record(CallRecord("a", "m", 0, None, Decimal("0.01"), 1.0))
    ledger.record(CallRecord("b", "m", 3, None, Decimal("0.05"), 1.0))
    assert ledger.total_by("provider_id") == {"a": Decimal("0.01"), "b": Decimal("0.05")}
    assert ledger.total_by("tier") == {0: Decimal("0.01"), 3: Decimal("0.05")}


def test_summary_mentions_the_t5_gate(ledger):
    ledger.record(CallRecord("a", "m", 0, "d", Decimal("0.01"), 1.0, pages=1))
    assert "T5 gate" in ledger.summary()


def test_env_var_can_tighten_the_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("VERUMETRIC_SPEND_LIMIT_USD", "5")
    led = SpendLedger.open(tmp_path / "s.jsonl")
    assert led.limit_usd == Decimal("5")


# --- budget checkpoints and projection (ADR-0008) ---------------------------


def test_the_default_limit_is_the_hundred_dollar_budget():
    from verumetric.costs import DEFAULT_LIMIT_USD

    assert DEFAULT_LIMIT_USD == Decimal("100")


def test_crossing_a_quarter_of_the_budget_is_announced(tmp_path, capsys):
    """A budget is only a constraint if you hear about it before it is gone."""
    led = SpendLedger.open(tmp_path / "s.jsonl", Decimal("100"))
    led.record(CallRecord("p", "m", 0, None, Decimal("26"), 1.0))
    assert "25% of budget" in capsys.readouterr().out


def test_each_checkpoint_announces_once(tmp_path, capsys):
    led = SpendLedger.open(tmp_path / "s.jsonl", Decimal("100"))
    led.record(CallRecord("p", "m", 0, None, Decimal("26"), 1.0))
    capsys.readouterr()
    led.record(CallRecord("p", "m", 0, None, Decimal("1"), 1.0))
    assert "25% of budget" not in capsys.readouterr().out


def test_one_call_can_cross_several_checkpoints(tmp_path, capsys):
    led = SpendLedger.open(tmp_path / "s.jsonl", Decimal("100"))
    led.record(CallRecord("p", "m", 0, None, Decimal("80"), 1.0))
    out = capsys.readouterr().out
    assert "25% of budget" in out and "75% of budget" in out


def test_budget_projection_reports_a_shortfall(tmp_path, capsys):
    """The staged plan only works if the projection is checked between stages."""
    import sys

    sys.path.insert(0, "tools")
    import budget

    path = tmp_path / "s.jsonl"
    led = SpendLedger.open(path, Decimal("100"))
    for _ in range(10):
        led.record(CallRecord("p", "m", 0, "d", Decimal("1.00"), 1.0, pages=1))

    code = budget.main(["--ledger", str(path), "--remaining-pages", "390", "--limit", "100"])
    assert code == 1
    assert "DOES NOT FIT" in capsys.readouterr().out


def test_budget_projection_reports_headroom(tmp_path, capsys):
    import sys

    sys.path.insert(0, "tools")
    import budget

    path = tmp_path / "s.jsonl"
    led = SpendLedger.open(path, Decimal("100"))
    for _ in range(10):
        led.record(CallRecord("p", "m", 0, "d", Decimal("0.02"), 1.0, pages=1))

    code = budget.main(["--ledger", str(path), "--remaining-pages", "390", "--limit", "100"])
    assert code == 0
    assert "fits, with" in capsys.readouterr().out


def test_projection_refuses_to_invent_a_denominator(tmp_path, capsys):
    import sys

    sys.path.insert(0, "tools")
    import budget

    path = tmp_path / "s.jsonl"
    SpendLedger.open(path, Decimal("100"))
    assert budget.main(["--ledger", str(path), "--limit", "100"]) == 0
    assert "nothing to project from" in capsys.readouterr().out
