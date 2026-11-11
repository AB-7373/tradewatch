"""The entry/exit state machine and the Runner that fills its orders."""
import json

import pytest

from signals import Cfg, Machine, Runner


def steps(machine, probs):
    return [machine.step(p) for p in probs]


# ---- Machine: persistence, hysteresis, cooldown --------------------------------

def test_enters_only_after_n_consecutive_strong_bars():
    m = Machine(Cfg(entry=0.8, exit=0.5, persist=3, cooldown=0))
    # a dip below entry resets the streak
    assert steps(m, [0.9, 0.9, 0.7, 0.9, 0.9, 0.9]) == [None, None, None, None, None, "ENTER"]


def test_hysteresis_holds_between_exit_and_entry_lines():
    m = Machine(Cfg(entry=0.8, exit=0.5, persist=1, cooldown=0))
    assert m.step(0.85) == "ENTER"
    # 0.79 .. 0.5 is below entry but not below exit -> stay in
    assert steps(m, [0.79, 0.6, 0.5]) == [None, None, None]
    assert m.step(0.49) == "EXIT"


def test_cooldown_blocks_reentry():
    m = Machine(Cfg(entry=0.8, exit=0.5, persist=1, cooldown=2))
    assert m.step(0.9) == "ENTER"
    assert m.step(0.1) == "EXIT"
    assert steps(m, [0.95, 0.95]) == [None, None]     # resting
    assert m.step(0.95) == "ENTER"


@pytest.mark.parametrize("kw", [dict(entry=0.6, exit=0.7), dict(entry=0.6, exit=0.6),
                                dict(persist=0), dict(cooldown=-1), dict(cost=-0.01)])
def test_bad_settings_are_rejected(kw):
    with pytest.raises(ValueError):
        Cfg(**kw)


# ---- Runner: next-bar-open fills ------------------------------------------------

def feed(runner, bars):
    """bars: list of (ts, open, close, p_up, p_down)"""
    for b in bars:
        runner.process(*b)
    return runner


CFG = Cfg(entry=0.8, exit=0.5, persist=1, cooldown=0, cost=0.0)


def test_entry_and_exit_fill_at_next_bar_open():
    r = feed(Runner(CFG), [
        ("t0", 100, 101, 0.9, 0.05),   # signal ENTER long (decided on t0 close)
        ("t1", 102, 103, 0.9, 0.05),   # filled at t1 OPEN = 102, not t0 close 101
        ("t2", 104, 105, 0.1, 0.05),   # signal EXIT
        ("t3", 106, 107, 0.1, 0.05),   # filled at t3 OPEN = 106
    ])
    (t,) = r.closed
    assert (t["signal_time"], t["entry_time"], t["entry_price"]) == ("t0", "t1", 102)
    assert (t["exit_time"], t["exit_price"]) == ("t3", 106)
    assert t["ret"] == pytest.approx(106 / 102 - 1)


def test_signal_on_last_bar_stays_pending():
    r = feed(Runner(CFG), [("t0", 100, 100, 0.2, 0.1), ("t1", 100, 101, 0.9, 0.05)])
    assert r.pending["long"] == "ENTER"
    assert r.all_trades() == []          # no next bar -> no trade yet


def test_open_trade_is_marked_at_last_close():
    r = feed(Runner(CFG), [("t0", 100, 100, 0.9, 0.0), ("t1", 100, 110, 0.9, 0.0)])
    (t,) = r.all_trades()
    assert t["status"] == "OPEN" and t["exit_price"] == 110 and t["exit_time"] == "t1"


def test_short_side_runs_independently():
    r = feed(Runner(CFG), [
        ("t0", 100, 100, 0.05, 0.9),
        ("t1", 100, 98, 0.05, 0.9),
        ("t2", 97, 96, 0.05, 0.1),
        ("t3", 95, 95, 0.05, 0.1),
    ])
    (t,) = r.closed
    assert t["side"] == "short" and t["entry_price"] == 100 and t["exit_price"] == 95
    assert t["ret"] == pytest.approx(0.05)


# ---- Runner state: save/restore is lossless (this is what live poll relies on) --

BARS = [(f"2026-01-01 {h:02d}:15", 100 + h, 100.5 + h, pu, pd_)
        for h, (pu, pd_) in enumerate([(0.9, 0.05), (0.9, 0.05), (0.3, 0.6), (0.1, 0.9),
                                       (0.05, 0.9), (0.05, 0.9), (0.2, 0.3), (0.9, 0.05),
                                       (0.9, 0.05), (0.9, 0.05), (0.4, 0.4), (0.1, 0.1)])]


def test_state_round_trips_through_json():
    r = feed(Runner(CFG), BARS[:5])
    saved = json.loads(json.dumps(r.to_dict()))      # exactly what state.json stores
    assert Runner(CFG, saved).to_dict() == r.to_dict()


@pytest.mark.parametrize("split", range(1, len(BARS)))
def test_chunked_run_equals_continuous_run(split):
    """Live poll = backtest done in pieces. Results must be identical."""
    continuous = feed(Runner(CFG), BARS)
    first = feed(Runner(CFG), BARS[:split])
    resumed = feed(Runner(CFG, json.loads(json.dumps(first.to_dict()))), BARS[split:])
    assert resumed.to_dict() == continuous.to_dict()
    assert resumed.all_trades() == continuous.all_trades()


def test_old_state_files_without_pending_still_load():
    old = {"machines": {s: {"in_pos": False, "streak": 0, "cool": 0} for s in ("long", "short")},
           "open": {"long": None, "short": None}, "closed": [], "last_ts": "2026-10-28 15:15:00+05:30"}
    r = Runner(CFG, old)
    assert r.pending == {"long": None, "short": None}
