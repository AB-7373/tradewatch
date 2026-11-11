"""Synthetic price data so tests never touch the network."""
import numpy as np
import pandas as pd


def fake_bars(n=80, seed=0, start="2026-01-05 09:15"):
    """n hourly OHLC bars with a random walk, timezone-aware like Yahoo's."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n, freq="h", tz="Asia/Kolkata")
    close = 20000 * np.exp(np.cumsum(rng.normal(0, 0.003, n)))
    open_ = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.0005, n))
    high = np.maximum(open_, close) * 1.001
    low = np.minimum(open_, close) * 0.999
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close}, index=idx)
