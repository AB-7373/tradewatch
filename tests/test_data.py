"""Live poll must ignore bars whose hour is still in progress."""
import pandas as pd

from data import drop_unfinished
from helpers import fake_bars


def test_drop_unfinished_keeps_only_complete_bars():
    bars = fake_bars(5, start="2026-11-11 09:15")      # 09:15 ... 13:15
    now = pd.Timestamp("2026-11-11 12:40", tz="Asia/Kolkata")
    kept = drop_unfinished(bars, now)
    # 11:15 bar ends at 12:15 (done); 12:15 bar ends at 13:15 (not done yet)
    assert kept.index[-1] == pd.Timestamp("2026-11-11 11:15", tz="Asia/Kolkata")
    assert len(kept) == 3


def test_drop_unfinished_boundary_and_timezones():
    bars = fake_bars(3, start="2026-11-11 09:15")
    exactly_done = pd.Timestamp("2026-11-11 10:15", tz="Asia/Kolkata")
    assert len(drop_unfinished(bars, exactly_done)) == 1
    # Same moment expressed in UTC must give the same answer
    assert len(drop_unfinished(bars, exactly_done.tz_convert("UTC"))) == 1
