def close_trade(o, ts, price, cost, status):
    entry = o["entry_price"]
    ret = price / entry - 1 if o["side"] == "long" else entry / price - 1
    ret -= cost                                   # trading costs (brokerage, slippage)
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
