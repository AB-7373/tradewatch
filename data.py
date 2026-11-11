import pandas as pd
import yfinance as yf
from config import TICKER

MARKET_TZ = "Asia/Kolkata"
BAR_LENGTH = pd.Timedelta(hours=1)


def get_bars(start, end, ticker=TICKER):
    """Hourly price bars. start/end are 'YYYY-MM-DD' (end is exclusive)."""
    df = yf.download(ticker, start=str(start), end=str(end), interval="1h",
                     auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close"]].dropna()
    if df.empty:
        raise RuntimeError("No data returned. Hourly data only goes back ~730 days, "
                           "markets are closed on weekends, and end must be after start.")
    if df.index.tz is None:
        df.index = df.index.tz_localize(MARKET_TZ)
    return df.tz_convert(MARKET_TZ)


def drop_unfinished(bars, now=None):
    """Remove any bar whose hour has not finished yet.

    Yahoo labels a bar by its START time, so the 14:15 bar is complete at 15:15.
    Live mode must not read a half-finished bar: its 'close' is just the latest
    tick, and since poll remembers the last bar it saw, it would never come back
    to fix it.

    Note: NIFTY's last bar of the day starts at 15:15 and the market closes at
    15:30, so that bar is really only 15 minutes long. This rule waits until
    16:15 to accept it, which is a little late but always safe.
    """
    now = pd.Timestamp.now(tz=MARKET_TZ) if now is None else pd.Timestamp(now)
    if now.tzinfo is None:
        now = now.tz_localize(MARKET_TZ)
    return bars[bars.index + BAR_LENGTH <= now]
