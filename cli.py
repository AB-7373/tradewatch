import argparse, json, sys
import pandas as pd
from pipeline import run_analysis, poll, summarize
from signals import Cfg


def build_parser():
    ap = argparse.ArgumentParser(description="TradeWatch: shadow-test an AI's market predictions "
                                             "(paper trading only).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("analyze", "poll"):
        p = sub.add_parser(name)
        p.add_argument("--predictor", default="baseline", choices=["baseline", "jev"])
        p.add_argument("--entry", type=float, default=0.85, help="confidence needed to enter")
        p.add_argument("--exit", type=float, default=0.60, help="exit when confidence drops below")
        p.add_argument("--persist", type=int, default=3, help="strong bars in a row before entering")
        p.add_argument("--cooldown", type=int, default=3, help="bars to rest after exiting")
        p.add_argument("--cost", type=float, default=0.0005,
                       help="round-trip cost as a fraction (0.0005 = 0.05%%)")
        if name == "analyze":
            p.add_argument("--start", required=True, help="YYYY-MM-DD")
            p.add_argument("--end", required=True, help="YYYY-MM-DD (exclusive)")
            p.add_argument("--capital", type=float, default=100000)
            p.add_argument("--json", action="store_true", help="print a JSON summary instead")
    return ap


def print_report(r, s):
    print(f"\nPeriod: {s['period'][0]}  ->  {s['period'][1]}")
    print(f"Bars graded: {s['bars_graded']}")
    print(f"Model accuracy:          {s['accuracy']:.1%}")
    print(f"Always guess '{s['majority_class']}':     {s['majority_accuracy']:.1%}   "
          f"<- the fair bar to beat (random among 3 = 33% only if outcomes were equally common)")
    print("What really happened:    " + "  ".join(f"{c} {v:.0%}" for c, v in s["class_freq"].items()))
    print("What the model picked:   " + "  ".join(f"{c} {v:.0%}" for c, v in s["picked_freq"].items()))

    print("\nCalibration (Brier score, lower is better; skill > 0 means better than lazy):")
    for c, v in r["report"]["classes"].items():
        verdict = "BETTER than lazy" if v["skill"] > 0 else "WORSE than lazy"
        print(f"  {c:5s} brier={v['brier']:.4f}  lazy={v['lazy_brier']:.4f}  "
              f"skill={v['skill']:+.3f}  -> {verdict}")
        print("    " + v["table"].round(3).to_string(index=False).replace("\n", "\n    "))

    t = r["trades"]
    print(f"\nTrades: {len(t)}" + (f"   wins: {s['wins']} ({s['win_rate']:.0%})" if t else
                                  "   (the filter refused to trade)"))
    if t:
        cols = ["side", "entry_time", "entry_price", "exit_time", "exit_price", "ret", "pnl", "status"]
        print(pd.DataFrame(t)[cols].round(4).to_string(index=False))
    if s["pending_orders"]:
        print(f"Signal on the last bar, not filled (no next bar yet): {s['pending_orders']}")
    print(f"\nStart Rs {s['start_capital']:,.0f}  ->  Final Rs {s['final_capital']:,.0f}  "
          f"({s['strategy_return']:+.2%})")
    print(f"Buy-and-hold over the same period, same cost: {s['buy_and_hold_return']:+.2%}")


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        cfg = Cfg(entry=a.entry, exit=a.exit, persist=a.persist, cooldown=a.cooldown, cost=a.cost)
        if a.cmd == "poll":
            print(json.dumps(poll(a.predictor, cfg), indent=2, default=str))
            return
        r = run_analysis(a.start, a.end, a.predictor, cfg, a.capital)
    except (ValueError, RuntimeError) as e:
        sys.exit(f"Error: {e}")
    s = summarize(r, cfg)
    if a.json:
        out = {**s, "trade_list": r["trades"]}
        print(json.dumps(out, indent=2, default=str))
    else:
        print_report(r, s)


if __name__ == "__main__":
    main()
