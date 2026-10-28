import argparse, json
import pandas as pd
from pipeline import run_analysis, poll
from signals import Cfg


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("analyze", "poll"):
        p = sub.add_parser(name)
        p.add_argument("--predictor", default="baseline", choices=["baseline", "jev"])
        p.add_argument("--entry", type=float, default=0.85)
        p.add_argument("--exit", type=float, default=0.60)
        p.add_argument("--persist", type=int, default=3)
        p.add_argument("--cooldown", type=int, default=3)
        if name == "analyze":
            p.add_argument("--start", required=True)
            p.add_argument("--end", required=True)
            p.add_argument("--capital", type=float, default=100000)
    a = ap.parse_args()
    cfg = Cfg(entry=a.entry, exit=a.exit, persist=a.persist, cooldown=a.cooldown)

    if a.cmd == "poll":
        print(json.dumps(poll(a.predictor, cfg), indent=2, default=str))
        return

    r = run_analysis(a.start, a.end, a.predictor, cfg, a.capital)
    rep = r["report"]
    print(f"\nBars graded: {rep['n']}   Accuracy: {rep['accuracy']:.1%} (random guessing among 3 = 33%)")
    for c, v in rep["classes"].items():
        verdict = "BETTER than lazy" if v["skill"] > 0 else "WORSE than lazy"
        print(f"  {c:5s} brier={v['brier']:.4f}  lazy={v['lazy_brier']:.4f}  skill={v['skill']:+.3f}  -> {verdict}")
        print(v["table"].round(3).to_string(index=False))
    t = r["trades"]
    print(f"\nTrades: {len(t)}")
    if t:
        print(pd.DataFrame(t)[["side", "entry_time", "exit_time", "ret", "pnl", "status"]].to_string(index=False))
    print(f"\nStart Rs {r['start_capital']:,.0f}  ->  Final Rs {r['final_capital']:,.0f}")


if __name__ == "__main__":
    main()
