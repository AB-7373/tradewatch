import numpy as np
import pandas as pd
from config import CLASSES


def make_labels(close, horizon, band):
    """What REALLY happened. Used only for grading, never shown to the model."""
    fut = close.shift(-horizon) / close - 1
    lab = pd.Series(np.where(fut > band, "up", np.where(fut < -band, "down", "flat")),
                    index=close.index)
    return lab.where(fut.notna())


def calibration_report(preds, labels):
    df = preds.join(labels.rename("label")).dropna(subset=["label"])
    out = {"n": len(df)}
    pcols = [f"p_{c}" for c in CLASSES]
    out["accuracy"] = float((df[pcols].idxmax(axis=1).str[2:] == df["label"]).mean())
    out["classes"] = {}
    for c in CLASSES:
        p = df[f"p_{c}"]
        y = (df["label"] == c).astype(float)
        brier = float(((p - y) ** 2).mean())                 # lower = better
        lazy = float(((y.mean() - y) ** 2).mean())           # always guess the average
        bins = pd.cut(p, np.linspace(0, 1, 11), include_lowest=True)
        table = (pd.DataFrame({"avg_predicted": p, "actual_freq": y})
                 .groupby(bins, observed=True)
                 .agg(avg_predicted=("avg_predicted", "mean"),
                      actual_freq=("actual_freq", "mean"),
                      count=("actual_freq", "size"))
                 .reset_index(drop=True))
        out["classes"][c] = {
            "brier": brier, "lazy_brier": lazy,
            "skill": (1 - brier / lazy) if lazy > 0 else float("nan"),  # below 0 = worse than lazy
            "table": table,
        }
    return out
