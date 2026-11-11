"""Run the Strict / Medium / Loose rule presets side by side against buy-and-hold.

usage: python compare.py START END [baseline] [jev] [--cost 0.0005]
"""
import argparse
import pandas as pd
from data import get_bars
from pipeline import run_analysis, summarize
from signals import Cfg

PRESETS = {
    "Strict (85%, 3 bars)": dict(entry=0.85, exit=0.60, persist=3, cooldown=3),
    "Medium (70%, 3 bars)": dict(entry=0.70, exit=0.50, persist=3, cooldown=3),
    "Loose (55%, 2 bars)":  dict(entry=0.55, exit=0.45, persist=2, cooldown=3),
}


def compare(start, end, predictors=("baseline",), cost=0.0005, capital=100000.0, bars=None):
    bars = get_bars(start, end) if bars is None else bars     # download once, reuse
    rows = []
    for pname in predictors:
        for sname, kw in PRESETS.items():
            cfg = Cfg(**kw, cost=cost)
            s = summarize(run_analysis(start, end, pname, cfg, capital, bars=bars), cfg)
            rows.append({
                "predictor": pname,
                "rules": sname,
                "trades": s["trades"],
                "win_rate_%": round(s["win_rate"] * 100) if s["trades"] else None,
                "final_capital": round(s["final_capital"]),
                "strategy_%": round(s["strategy_return"] * 100, 2),
                "buy_and_hold_%": round(s["buy_and_hold_return"] * 100, 2),
                "accuracy_%": round(s["accuracy"] * 100, 1),
                "always_majority_%": round(s["majority_accuracy"] * 100, 1),
            })
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("start")
    ap.add_argument("end")
    ap.add_argument("predictors", nargs="*", default=["baseline"], choices=["baseline", "jev"])
    ap.add_argument("--cost", type=float, default=0.0005)
    a = ap.parse_args()
    df = compare(a.start, a.end, a.predictors or ["baseline"], a.cost)
    print(df.to_string(index=False))
    print("\n(accuracy does not change between presets: the rules filter trades, not predictions)")
    df.to_csv("comparison.csv", index=False)
    print("Saved comparison.csv")


if __name__ == "__main__":
    main()
