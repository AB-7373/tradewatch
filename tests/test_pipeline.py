"""End-to-end backtest and live poll on fake data (no network)."""
import json

import pandas as pd
import pytest

import pipeline
from helpers import fake_bars
from signals import Cfg

LOOSE = Cfg(entry=0.55, exit=0.45, persist=2, cooldown=1)


def test_backtest_runs_and_compounds():
    r = pipeline.run_analysis("x", "y", "baseline", LOOSE, 100000, bars=fake_bars(400, seed=3))
    assert r["trades"], "loose settings on a random walk should produce some trades"
    assert r["final_capital"] == pytest.approx(r["trades"][-1]["equity"])
    s = pipeline.summarize(r, LOOSE)
    json.dumps(s)                                     # summary must be JSON-ready
    assert s["trades"] == len(r["trades"])


def test_equity_curve_starts_at_capital_and_ends_at_final():
    r = pipeline.run_analysis("x", "y", "baseline", LOOSE, 100000, bars=fake_bars(400, seed=3))
    curve = pipeline.equity_curve(r["feats"], r["trades"], 100000)
    assert curve.iloc[0] == pytest.approx(100000)
    # last value = final capital, except the round-trip cost of a still-open trade
    open_cost = sum(1 for t in r["trades"] if t["status"] == "OPEN") * LOOSE.cost * 100000
    assert curve.iloc[-1] == pytest.approx(r["final_capital"], abs=open_cost * 1.2 + 1)


def test_bundled_sample_used_when_yahoo_fails(monkeypatch):
    import data

    def boom(*a, **k):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(data, "get_bars", boom)
    bars, source = data.load_bars("2026-09-01", "2026-10-01")
    assert source == "sample" and len(bars) > 100
    assert bars.index.min() >= pd.Timestamp("2026-09-01", tz="Asia/Kolkata")


def test_backtest_decisions_do_not_depend_on_future_bars():
    """Trades that finished before bar N are identical whether or not we also
    feed the bars after N. If the past changed, the future was leaking in."""
    bars = fake_bars(400, seed=5)
    short = pipeline.run_analysis("x", "y", "baseline", LOOSE, 100000, bars=bars.iloc[:250])
    full = pipeline.run_analysis("x", "y", "baseline", LOOSE, 100000, bars=bars)
    done = lambda r: [t for t in r["trades"] if t["status"] == "CLOSED"]
    assert done(short) and done(short) == done(full)[:len(done(short))]


def test_poll_only_processes_new_finished_bars(tmp_path, monkeypatch):
    bars = fake_bars(200, seed=7, start="2026-11-01 09:15")
    clock = {"now": bars.index[120] + pd.Timedelta(minutes=30)}   # bar 120 still in progress
    monkeypatch.setattr(pipeline, "get_bars", lambda start, end: bars)
    monkeypatch.setattr(pipeline, "drop_unfinished",
                        lambda b: b[b.index + pd.Timedelta(hours=1) <= clock["now"]])
    state = str(tmp_path / "state.json")

    first = pipeline.poll("baseline", LOOSE, state_file=state)
    assert first["new_bars"] == 10                                # warm-up
    assert first["last_bar"] == str(bars.index[119])              # unfinished bar 120 skipped

    assert pipeline.poll("baseline", LOOSE, state_file=state)["new_bars"] == 0

    clock["now"] = bars.index[125] + pd.Timedelta(hours=1)
    third = pipeline.poll("baseline", LOOSE, state_file=state)
    assert third["new_bars"] == 6 and third["last_bar"] == str(bars.index[125])
