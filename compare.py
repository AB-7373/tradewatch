import sys
import pandas as pd
from pipeline import run_analysis
from signals import Cfg

SCENARIOS = {
    "Strict (85%, 3 bars)": Cfg(entry=0.85, exit=0.60, persist=3, cooldown=3),
    "Medium (70%, 3 bars)": Cfg(entry=0.70, exit=0.50, persist=3, cooldown=3),
    "Loose (55%, 2 bars)":  Cfg(entry=0.55, exit=0.45, persist=2, cooldown=3),
}

def main(start, end, predictors):
    rows = []
    for pname in predictors:
        for sname, cfg in SCENARIOS.items():
            r = run_analysis(start, end, pname, cfg, 100000)
            t = r["trades"]
            close = r["feats"]["close"]
            wins = sum(1 for x in t if x["ret"] > 0)
            rows.append({
                "predictor": pname,
                "rules": sname,
                "trades": len(t),
                "win_rate": f"{wins / len(t):.0%}" if t else "-",
                "final_capital": round(r["final_capital"]),
                "profit_%": round((r["final_capital"] / 100000 - 1) * 100, 2),
                "accuracy_%": round(r["report"]["accuracy"] * 100, 1),
                "buy_and_hold_%": round((close.iloc[-1] / close.iloc[0] - 1) * 100, 2),
            })
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    df.to_csv("comparison.csv", index=False)

if __name__ == "__main__":
    # usage: python compare.py 2026-07-01 2026-10-01 baseline jev
    main(sys.argv[1], sys.argv[2], sys.argv[3:] or ["baseline"])
