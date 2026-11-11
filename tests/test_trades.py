"""Return math for long and short trades, cost deduction and compounding."""
import pytest

from trades import apply_capital, close_trade


def _ret(side, entry, exit_, cost=0.0):
    o = {"side": side, "entry_time": "t0", "entry_price": entry}
    return close_trade(o, "t1", exit_, cost, "CLOSED")["ret"]


def test_long_returns():
    assert _ret("long", 100, 110) == pytest.approx(0.10)
    assert _ret("long", 100, 90) == pytest.approx(-0.10)


def test_short_returns():
    # Short = sell at 100, buy back later. Falling price is a gain.
    assert _ret("short", 100, 90) == pytest.approx(0.10)
    assert _ret("short", 100, 50) == pytest.approx(0.50)      # old formula said +100%
    assert _ret("short", 100, 110) == pytest.approx(-0.10)
    assert _ret("short", 100, 200) == pytest.approx(-1.00)    # old formula said -50%


def test_cost_is_deducted_once_per_round_trip():
    assert _ret("long", 100, 110, cost=0.0005) == pytest.approx(0.10 - 0.0005)
    assert _ret("short", 100, 90, cost=0.0005) == pytest.approx(0.10 - 0.0005)
    assert _ret("long", 100, 100, cost=0.001) == pytest.approx(-0.001)


def test_apply_capital_compounds_in_exit_order():
    trades = [
        {"exit_time": "2026-01-02", "ret": -0.10},
        {"exit_time": "2026-01-01", "ret": 0.10},
    ]
    out, final = apply_capital(trades, 1000.0)
    assert [t["exit_time"] for t in out] == ["2026-01-01", "2026-01-02"]
    assert out[0]["pnl"] == pytest.approx(100.0)
    assert out[1]["pnl"] == pytest.approx(-110.0)
    assert final == pytest.approx(990.0)
