import pandas as pd
import yfinance as yf
from config import TICKER


def get_bars(start, end, ticker=TICKER):
    """Hourly price bars. start/end are 'YYYY-MM-DD' (end is exclusive)."""
    df = yf.download(ticker, start=start, end=end, interval="1h",
                     auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close"]].dropna()
    if df.empty:
        raise RuntimeError("No data returned. Hourly data only goes back ~730 days.")
    return df
