import json, os
import pandas as pd
import config
from data import MARKET_TZ, drop_unfinished, get_bars
from features import add_features
from predictor import BaselinePredictor, JevPredictor
from calibration import make_labels, calibration_report
from signals import Cfg, Runner
from trades import apply_capital


def build_predictor(name):
    return JevPredictor() if name == "jev" else BaselinePredictor()


def predict_frame(feats, predictor):
    rows = [predictor.predict(ts, row) for ts, row in feats.iterrows()]
    predictor.flush()
    return pd.DataFrame(rows, index=feats.index)


def replay(runner, feats, preds):
    """Feed bars to the Runner one at a time, in order. The ONLY place the
    Runner is driven, for both backtest and live poll."""
    for ts in feats.index:
        runner.process(ts, feats.at[ts, "open"], feats.at[ts, "close"],
                       preds.at[ts, "p_up"], preds.at[ts, "p_down"])
    return runner


def run_analysis(start, end, predictor_name="baseline", cfg=None, capital=100000.0, bars=None):
    """Backtest. Pass `bars` to reuse already-downloaded prices."""
    cfg = cfg or Cfg()
    bars = get_bars(start, end) if bars is None else bars
    feats = add_features(bars)
    preds = predict_frame(feats, build_predictor(predictor_name))
    labels = make_labels(feats["close"], config.HORIZON, config.FLAT_BAND)
    report = calibration_report(preds, labels)

    runner = replay(Runner(cfg), feats, preds)      # bar by bar, like live
    trades, final = apply_capital(runner.all_trades(), capital)
    return {"feats": feats, "preds": preds, "labels": labels, "report": report,
            "trades": trades, "pending": runner.pending,
            "start_capital": capital, "final_capital": final}


def buy_and_hold(feats, cost):
    """Benchmark: buy at the first bar's open, sell at the last close, pay the same cost."""
    return float(feats["close"].iloc[-1] / feats["open"].iloc[0] - 1 - cost)


def equity_curve(feats, trades, capital):
    """Account value at every bar: banked P&L of finished trades plus the
    paper gain/loss of any trade still running (marked at each bar's close)."""
    close = feats["close"]
    value = pd.Series(float(capital), index=feats.index)
    for t in trades:                        # trades as returned by apply_capital
        entry, exit_ = pd.Timestamp(t["entry_time"]), pd.Timestamp(t["exit_time"])
        stake = t["equity"] - t["pnl"]       # account size when this trade's result is booked
        move = close / t["entry_price"] - 1
        gross = move if t["side"] == "long" else -move
        running = (feats.index >= entry) & (feats.index < exit_)
        value[running] += stake * gross[running]
        value[feats.index >= exit_] += t["pnl"]
    return value


def summarize(r, cfg):
    """Plain, JSON-ready summary of a backtest. The CLI, compare.py and the
    dashboard all use this, so they always show the same numbers."""
    rep, t = r["report"], r["trades"]
    wins = sum(1 for x in t if x["ret"] > 0)
    return {
        "period": [str(r["feats"].index[0]), str(r["feats"].index[-1])],
        "bars_graded": rep["n"],
        "accuracy": rep["accuracy"],
        "majority_class": rep["majority_class"],
        "majority_accuracy": rep["majority_accuracy"],
        "class_freq": rep["class_freq"],
        "picked_freq": rep["picked_freq"],
        "brier": {c: {k: v[k] for k in ("brier", "lazy_brier", "skill")}
                  for c, v in rep["classes"].items()},
        "settings": {"entry": cfg.entry, "exit": cfg.exit, "persist": cfg.persist,
                     "cooldown": cfg.cooldown, "cost": cfg.cost},
        "trades": len(t),
        "wins": wins,
        "win_rate": wins / len(t) if t else None,
        "pending_orders": {k: v for k, v in r["pending"].items() if v},
        "start_capital": r["start_capital"],
        "final_capital": r["final_capital"],
        "strategy_return": r["final_capital"] / r["start_capital"] - 1,
        "buy_and_hold_return": buy_and_hold(r["feats"], cfg.cost),
    }


def poll_step(state, predictor_name="baseline", cfg=None):
    """One live check, given the saved state (or None on the first run).
    Only NEW, finished bars since the last check are processed."""
    cfg = cfg or Cfg()
    runner = Runner(cfg, state)
    today = pd.Timestamp.now(tz=MARKET_TZ).normalize()
    bars = get_bars((today - pd.Timedelta(days=12)).date(),
                    (today + pd.Timedelta(days=1)).date())
    feats = add_features(drop_unfinished(bars))     # never consume a half-finished bar
    if runner.last_ts:
        feats = feats[feats.index > pd.Timestamp(runner.last_ts)]
    else:
        feats = feats.tail(10)                      # first run: warm up on the last 10 bars
    if feats.empty:
        return {"new_bars": 0, "last_bar": runner.last_ts,
                "positions": runner.all_trades(), "state": runner.to_dict()}
    preds = predict_frame(feats, build_predictor(predictor_name))
    replay(runner, feats, preds)
    return {"new_bars": len(feats), "last_bar": runner.last_ts,
            "last_probs": {k: round(float(v), 4) for k, v in preds.iloc[-1].items()},
            "positions": runner.all_trades(), "state": runner.to_dict()}


def poll(predictor_name="baseline", cfg=None, state_file=None):
    """Live mode for the CLI: state is remembered in state.json between runs."""
    state_file = state_file or config.STATE_FILE
    state = None
    if os.path.exists(state_file):
        with open(state_file) as f:
            state = json.load(f)
    out = poll_step(state, predictor_name, cfg)
    if out["new_bars"]:
        with open(state_file, "w") as f:
            json.dump(out["state"], f, indent=2)
    return out
