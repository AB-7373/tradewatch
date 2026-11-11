"""No-lookahead features, an anonymous prompt, and a prompt-aware cache."""
import pandas as pd

import config
from features import add_features, describe
from helpers import fake_bars
from predictor import BaselinePredictor, JevPredictor


def test_features_do_not_change_when_future_bars_are_added():
    bars = fake_bars(120)
    past_only = add_features(bars.iloc[:80])
    with_future = add_features(bars)
    pd.testing.assert_frame_equal(past_only, with_future.loc[past_only.index])


def test_describe_leaks_no_date_or_name():
    feats = add_features(fake_bars(60))
    ts, row = next(feats.iterrows())
    text = describe(row)
    assert "NIFTY" not in text.upper()
    assert str(ts.year) not in text
    assert ts.strftime("%Y-%m-%d") not in text
    assert "return" in text and "volatility" in text


def test_baseline_probabilities_sum_to_one():
    feats = add_features(fake_bars(60))
    p = BaselinePredictor()
    for ts, row in feats.iterrows():
        out = p.predict(ts, row)
        assert abs(out["p_up"] + out["p_down"] + out["p_flat"] - 1) < 1e-9


def test_jev_cache_key_depends_on_prompt_text(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_FILE", str(tmp_path / "cache.json"))
    calls = []

    def fake_ask(self, state):
        calls.append(state)
        return {"answers": {"direction": {"probabilities": {"up": 0.5, "down": 0.3, "flat": 0.2}}}}

    monkeypatch.setattr(JevPredictor, "_ask", fake_ask)
    feats = add_features(fake_bars(60))
    (ts, row_a), (_, row_b) = list(feats.iterrows())[:2]

    jev = JevPredictor()
    jev.predict(ts, row_a)
    jev.predict(ts, row_a)          # same timestamp + same text -> cached, no new call
    assert len(calls) == 1
    jev.predict(ts, row_b)          # same timestamp, different text -> must ask again
    assert len(calls) == 2
