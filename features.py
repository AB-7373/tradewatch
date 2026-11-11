import numpy as np
import pandas as pd


def add_features(bars):
    """Everything here uses only the current and PAST bars (no lookahead)."""
    c = bars["Close"]
    logc = np.log(c)
    r = logc.diff()
    f = pd.DataFrame(index=bars.index)
    f["open"] = bars["Open"]   # not a model input; used to fill orders at the next bar's open
    f["close"] = c
    f["ret_1h"] = r
    f["ret_5h"] = logc.diff(5)
    f["ret_20h"] = logc.diff(20)
    f["vol_20h"] = r.rolling(20).std()          # how jumpy price has been
    f["trend"] = c / c.rolling(20).mean() - 1   # price vs its 20-hour average
    return f.dropna()


def describe(row):
    """Turn numbers into a short text the AI reads as its 'state'.

    Deliberately anonymous: no date and no index name. A language model may have
    read news about a given week, so telling it "NIFTY 50 on 2026-10-07" could leak
    what happened next. It only gets the numbers.
    """
    return (f"An equity index, hourly bars. Last 1h return {row.ret_1h*100:.2f}%, "
            f"5h return {row.ret_5h*100:.2f}%, 20h return {row.ret_20h*100:.2f}%, "
            f"hourly volatility {row.vol_20h*100:.2f}%, price vs 20h average {row.trend*100:.2f}%.")
