def close_trade(o, ts, price, cost, status):
    """Turn an open position into a finished trade with a % return.

    long : bought at entry, sold at price  -> price / entry - 1
    short: sold at entry, bought back at price -> 1 - price / entry
           (e.g. short at 100, price doubles to 200 -> -100%, you lost your stake)
    """
    entry = o["entry_price"]
    ret = price / entry - 1 if o["side"] == "long" else 1 - price / entry
    ret -= cost                                   # round-trip trading costs (brokerage, slippage)
    return {**o, "exit_time": str(ts), "exit_price": float(price),
            "ret": ret, "status": status}


def apply_capital(trades, capital):
    """Compound the account through trades in order of exit time.
    Simplification: long and short trades are chained as if capital is fully reused."""
    equity = capital
    out = sorted(trades, key=lambda t: t["exit_time"])
    for t in out:
        t["pnl"] = equity * t["ret"]
        equity += t["pnl"]
        t["equity"] = equity
    return out, equity
