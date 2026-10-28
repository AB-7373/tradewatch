import json, os
import pandas as pd
import config
from data import get_bars
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


def run_analysis(start, end, predictor_name="baseline", cfg=None, capital=100000.0):
    cfg = cfg or Cfg()
    feats = add_features(get_bars(start, end))
    preds = predict_frame(feats, build_predictor(predictor_name))
    labels = make_labels(feats["close"], config.HORIZON, config.FLAT_BAND)
    report = calibration_report(preds, labels)

    runner = Runner(cfg)
    for ts in feats.index:                          # bar by bar, like live
        runner.process(ts, feats.at[ts, "close"], preds.at[ts, "p_up"], preds.at[ts, "p_down"])
    trades = runner.all_trades(feats["close"].iloc[-1], feats.index[-1])
    trades, final = apply_capital(trades, capital)
    return {"feats": feats, "preds": preds, "report": report,
            "trades": trades, "start_capital": capital, "final_capital": final}


def poll(predictor_name="baseline", cfg=None):
    """Live mode: only looks at NEW bars since last run. Run it by hand."""
    cfg = cfg or Cfg()
    state = None
    if os.path.exists(config.STATE_FILE):
        with open(config.STATE_FILE) as f:
            state = json.load(f)
    runner = Runner(cfg, state)
    today = pd.Timestamp.today().normalize()
    feats = add_features(get_bars((today - pd.Timedelta(days=12)).date(),
                                  (today + pd.Timedelta(days=1)).date()))
    if runner.last_ts:
        feats = feats[feats.index.astype(str) > runner.last_ts]
    else:
        feats = feats.tail(10)                      # first run: warm up on the last 10 bars
    if feats.empty:
        return {"new_bars": 0, "state": runner.to_dict()}
    preds = predict_frame(feats, build_predictor(predictor_name))
    for ts in feats.index:
        runner.process(ts, feats.at[ts, "close"], preds.at[ts, "p_up"], preds.at[ts, "p_down"])
    with open(config.STATE_FILE, "w") as f:
        json.dump(runner.to_dict(), f, indent=2)
    return {"new_bars": len(feats), "last_probs": preds.iloc[-1].to_dict(),
            "state": runner.to_dict()}
