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


def poll(predictor_name="baseline", cfg=None, state_file=None):
    """Live mode: only looks at NEW, finished bars since last run. Run it by hand."""
    cfg = cfg or Cfg()
    state_file = state_file or config.STATE_FILE
    state = None
    if os.path.exists(state_file):
        with open(state_file) as f:
            state = json.load(f)
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
        return {"new_bars": 0, "last_bar": runner.last_ts, "state": runner.to_dict()}
    preds = predict_frame(feats, build_predictor(predictor_name))
    replay(runner, feats, preds)
    with open(state_file, "w") as f:
        json.dump(runner.to_dict(), f, indent=2)
    return {"new_bars": len(feats), "last_bar": runner.last_ts,
            "last_probs": {k: round(float(v), 4) for k, v in preds.iloc[-1].items()},
            "positions": runner.all_trades(), "state": runner.to_dict()}
