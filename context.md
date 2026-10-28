TradeWatch: Full Build Guide, Code and Context
A beginner-friendly side project: test whether an AI's stock predictions can be trusted, using paper trades only (no real money).
0. Context (paste this into a new chat if you ever need to resume)
• Project: TradeWatch, a "shadow-testing harness". It replays old NIFTY hourly prices bar by bar, asks an AI (Jev / OpenJev) for the chance of up / down / flat over the next few hours, grades how honest those chances are (calibration), applies a strict entry/exit rule, and counts paper profit in rupees. It never places real orders.
• User level: beginner. Explain jargon in brackets in plain language.
• Goal: build it, deploy it (Streamlit Community Cloud), then report and explain it to someone.
• AI model: Jev is TypeSafe AI's hosted model and is not open source. OpenJev (github.com/razorback16/openjev) is an independent open-source server that copies Jev's API (POST /v1/systemone). It can be used hosted at https://api.codiv.ai (free signup on codiv.ai, key looks like sk-codiv-...) or run on your own GPU or Mac. It is not affiliated with TypeSafe.
• Fallback: a simple BaselinePredictor (formula-based) so everything runs without any API key.
• Known result from the original idea: with strict settings (85% confidence for several hours in a row) the real Jev gave no tradeable signals and was poorly calibrated. The system correctly refused to trust it. That is a valid, honest result, not a failure.
• Data limit: Yahoo Finance gives only about 730 days of hourly data.
1. Key terms in plain language
• Backtest (replaying old data as if it were live).
• Lookahead / data leakage (accidentally letting the AI see the future, which makes the test fake). Our features use only past bars.
• Calibration (does "80% sure" really come true about 80% of the time?).
• Brier score (a report card for probability guesses; lower is better). We compare it with a lazy baseline that always guesses the average. If the model scores worse than lazy, it has no skill.
• Persistence filter (only act if confidence stays high for several hours in a row, to ignore one-off flukes).
• Hysteresis (once in a trade, exit only when confidence drops clearly below a lower line, not on a tiny dip).
• Cooldown (a rest period after exiting before a new entry).
• Long / short (long = buy first and sell later, profit if price rises; short = sell first and buy back later, profit if price falls).
• Shadow test (paper trading only).
2. Workflow
1. Download hourly prices (data.py).
2. Compute simple past-only features (features.py).
3. Ask the predictor for P(up), P(down), P(flat) (predictor.py).
4. Grade against what really happened (calibration.py).
5. Run the entry/exit state machine, the same code for backtest and live (signals.py).
6. Convert trades to rupees (trades.py).
7. Show results in the terminal (cli.py) and on a web page (app.py).
3. Setup
mkdir tradewatch && cd tradewatch
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
To use OpenJev (optional), set these before running:
export TYPESAFE_BASE_URL=https://api.codiv.ai
export TYPESAFE_API_KEY=sk-codiv-xxxx
Windows PowerShell: $env:TYPESAFE_API_KEY="sk-codiv-xxxx".
4. The code
Create each file below inside the tradewatch folder.
requirements.txt
pandas
numpy
yfinance
requests
streamlit
config.py
import os

BASE_URL = os.getenv("TYPESAFE_BASE_URL", "https://api.codiv.ai")
API_KEY = os.getenv("TYPESAFE_API_KEY", "")
MODEL = os.getenv("JEV_MODEL", "openjev-latest")

TICKER = "^NSEI"      # NIFTY 50 on Yahoo Finance
HORIZON = 3           # predict this many hourly bars ahead
FLAT_BAND = 0.001     # moves smaller than +/-0.1% count as "flat"
CLASSES = ("up", "down", "flat")

CACHE_FILE = "jev_cache.json"
STATE_FILE = "state.json"
data.py
import pandas as pd
import yfinance as yf
from config import TICKER


def get_bars(start, end, ticker=TICKER):
    """Hourly price bars. start/end are 'YYYY-MM-DD' (end is exclusive)."""
    df = yf.download(ticker, start=start, end=end, interval="1h",
                     auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close"]].dropna()
    if df.empty:
        raise RuntimeError("No data returned. Hourly data only goes back ~730 days.")
    return df
features.py
import numpy as np
import pandas as pd


def add_features(bars):
    """Everything here uses only the current and PAST bars (no lookahead)."""
    c = bars["Close"]
    logc = np.log(c)
    r = logc.diff()
    f = pd.DataFrame(index=bars.index)
    f["close"] = c
    f["ret_1h"] = r
    f["ret_5h"] = logc.diff(5)
    f["ret_20h"] = logc.diff(20)
    f["vol_20h"] = r.rolling(20).std()          # how jumpy price has been
    f["trend"] = c / c.rolling(20).mean() - 1   # price vs its 20-hour average
    return f.dropna()


def describe(ts, row):
    """Turn numbers into a short text the AI reads as its 'state'."""
    return (f"NIFTY 50 index, hourly bars. As of {ts}: last 1h return {row.ret_1h*100:.2f}%, "
            f"5h return {row.ret_5h*100:.2f}%, 20h return {row.ret_20h*100:.2f}%, "
            f"hourly volatility {row.vol_20h*100:.2f}%, price vs 20h average {row.trend*100:.2f}%.")
predictor.py
import json, os, time
import numpy as np
import requests
import config
from features import describe


class BaselinePredictor:
    """Simple formula guesser. Works with no API key."""
    name = "baseline"

    def predict(self, ts, row):
        z = row.trend / (row.vol_20h * np.sqrt(20) + 1e-9)   # trend measured in 'volatility units'
        logits = np.array([z, -z, 0.0])
        p = np.exp(logits - logits.max())
        p /= p.sum()
        return {"p_up": p[0], "p_down": p[1], "p_flat": p[2]}

    def flush(self):
        pass


class JevPredictor:
    """Talks to Jev / OpenJev. Answers are cached on disk so re-runs cost nothing."""
    name = "jev"

    def __init__(self):
        self.cache = {}
        self.new_calls = 0
        if os.path.exists(config.CACHE_FILE):
            with open(config.CACHE_FILE) as f:
                self.cache = json.load(f)

    def _ask(self, state):
        h, b = config.HORIZON, config.FLAT_BAND * 100
        body = {
            "model": config.MODEL,
            "state": state,
            "questions": {"direction": {
                "type": "choice",
                "instructions": f"Over the next {h} hourly bars, will the index close up, down, or flat?",
                "criteria": {
                    "up": f"rises by more than {b:.1f}%",
                    "down": f"falls by more than {b:.1f}%",
                    "flat": f"moves less than {b:.1f}% either way",
                }}},
        }
        headers = {"Authorization": f"Bearer {config.API_KEY}"}
        for attempt in range(4):
            r = requests.post(f"{config.BASE_URL}/v1/systemone", json=body,
                              headers=headers, timeout=60)
            if r.status_code in (429, 529):      # busy or rate-limited: wait and retry
                time.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError("Model API kept returning busy/rate-limit errors.")

    @staticmethod
    def _parse(resp):
        ans = resp["answers"]["direction"]
        probs = ans["probabilities"]
        if isinstance(probs, list):                # list in the order up, down, flat
            probs = dict(zip(config.CLASSES, probs))
        return {f"p_{c}": float(probs.get(c, 0.0)) for c in config.CLASSES}

    def predict(self, ts, row):
        key = f"{config.MODEL}|{ts}|{config.HORIZON}|{config.FLAT_BAND}"
        if key not in self.cache:
            self.cache[key] = self._parse(self._ask(describe(ts, row)))
            self.new_calls += 1
            if self.new_calls % 20 == 0:
                self.flush()
        return self.cache[key]

    def flush(self):
        with open(config.CACHE_FILE, "w") as f:
            json.dump(self.cache, f)
If the first real call errors on parsing, print resp once. The shape documented by OpenJev is answers -> direction -> {choice, probabilities, confidence}; adjust _parse if your server differs.
calibration.py
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
trades.py
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
signals.py (the heart of the project)
from dataclasses import dataclass
from trades import close_trade


@dataclass
class Cfg:
    entry: float = 0.85     # confidence needed to count as a strong signal
    exit: float = 0.60      # confidence below this means 'get out' (hysteresis)
    persist: int = 3        # strong signal needed this many bars in a row
    cooldown: int = 3       # bars to wait after exiting
    cost: float = 0.0005    # 0.05% per round trip


class Machine:
    """Watches ONE probability stream (P(up) for longs, P(down) for shorts)."""

    def __init__(self, cfg):
        self.cfg, self.in_pos, self.streak, self.cool = cfg, False, 0, 0

    def step(self, p):
        c = self.cfg
        if self.in_pos:
            if p < c.exit:
                self.in_pos, self.cool, self.streak = False, c.cooldown, 0
                return "EXIT"
            return None
        if self.cool > 0:
            self.cool -= 1
            self.streak = 0
            return None
        self.streak = self.streak + 1 if p >= c.entry else 0
        if self.streak >= c.persist:
            self.in_pos = True
            return "ENTER"
        return None

    def to_dict(self):
        return {"in_pos": self.in_pos, "streak": self.streak, "cool": self.cool}


class Runner:
    """Used by BOTH backtest and live poll, so they can never drift apart."""
    SIDES = ("long", "short")

    def __init__(self, cfg, state=None):
        self.cfg = cfg
        self.m = {s: Machine(cfg) for s in self.SIDES}
        self.open = {s: None for s in self.SIDES}
        self.closed, self.last_ts = [], None
        if state:
            for s in self.SIDES:
                for k, v in state["machines"][s].items():
                    setattr(self.m[s], k, v)
            self.open, self.closed, self.last_ts = state["open"], state["closed"], state["last_ts"]

    def process(self, ts, price, p_up, p_down):
        for side, p in (("long", p_up), ("short", p_down)):
            ev = self.m[side].step(p)
            if ev == "ENTER":
                self.open[side] = {"side": side, "entry_time": str(ts), "entry_price": float(price)}
            elif ev == "EXIT" and self.open[side]:
                self.closed.append(close_trade(self.open[side], ts, price, self.cfg.cost, "CLOSED"))
                self.open[side] = None
        self.last_ts = str(ts)

    def all_trades(self, last_price, last_ts):
        """Closed trades plus any still-open ones marked at the latest price."""
        t = list(self.closed)
        for o in self.open.values():
            if o:
                t.append(close_trade(o, last_ts, last_price, self.cfg.cost, "OPEN"))
        return t

    def to_dict(self):
        return {"machines": {s: self.m[s].to_dict() for s in self.SIDES},
                "open": self.open, "closed": self.closed, "last_ts": self.last_ts}
pipeline.py
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
cli.py
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
app.py (the web page)
import os
import streamlit as st

try:   # on Streamlit Cloud, keys live in 'Secrets'
    for k in ("TYPESAFE_API_KEY", "TYPESAFE_BASE_URL"):
        if k in st.secrets:
            os.environ[k] = st.secrets[k]
except Exception:
    pass

import pandas as pd
from pipeline import run_analysis, poll
from signals import Cfg

st.set_page_config(page_title="TradeWatch", layout="wide")
st.title("TradeWatch")
st.caption("Shadow test: can an AI's confidence be trusted? Paper trades only, no real orders.")

with st.sidebar:
    predictor = st.selectbox("Predictor", ["baseline", "jev"])
    start = st.date_input("Start", pd.Timestamp.today() - pd.Timedelta(days=90))
    end = st.date_input("End", pd.Timestamp.today())
    capital = st.number_input("Starting capital (Rs)", value=100000.0, step=10000.0)
    entry = st.slider("Entry confidence", 0.50, 0.99, 0.85)
    exit_ = st.slider("Exit confidence", 0.30, 0.95, 0.60)
    persist = st.slider("Bars in a row", 1, 8, 3)
    cooldown = st.slider("Cooldown bars", 0, 8, 3)
    st.warning("The 'jev' predictor makes paid or limited API calls. Start with a short date range.")

cfg = Cfg(entry=entry, exit=exit_, persist=persist, cooldown=cooldown)
tab1, tab2 = st.tabs(["Backtest", "Live poll"])

with tab1:
    if st.button("Run backtest"):
        with st.spinner("Running..."):
            r = run_analysis(str(start), str(end), predictor, cfg, capital)
        rep = r["report"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Accuracy", f"{rep['accuracy']:.1%}", help="Random guessing among 3 outcomes is about 33%")
        c2.metric("Trades", len(r["trades"]))
        c3.metric("Final capital", f"Rs {r['final_capital']:,.0f}",
                  f"{r['final_capital'] - capital:+,.0f}")
        st.subheader("Calibration report card")
        for c, v in rep["classes"].items():
            ok = v["skill"] > 0
            st.markdown(f"**{c.upper()}**: Brier {v['brier']:.4f} vs lazy {v['lazy_brier']:.4f} "
                        f"({'better' if ok else 'worse'} than guessing the average)")
            st.bar_chart(v["table"].set_index("avg_predicted")["actual_freq"])
        st.subheader("Price")
        st.line_chart(r["feats"]["close"])
        st.subheader("Trades")
        if r["trades"]:
            st.dataframe(pd.DataFrame(r["trades"]))
        else:
            st.info("No trades passed the filter. That means the filter refused to trust the signal.")

with tab2:
    st.write("Checks only new bars since the last run. Manual on purpose, so no surprise API bills.")
    if st.button("Poll now"):
        st.json(poll(predictor, cfg))
    st.caption("On Streamlit Cloud the saved state can reset when the app restarts.")
5. Run it
# Offline, free, no key needed:
python cli.py analyze --start 2026-07-01 --end 2026-10-01 --predictor baseline

# Loosen the filter to see some trades (just to check the mechanics work):
python cli.py analyze --start 2026-07-01 --end 2026-10-01 --entry 0.55 --persist 2 --exit 0.45

# With OpenJev (try a SHORT range first, like 1 week):
python cli.py analyze --start 2026-10-01 --end 2026-10-08 --predictor jev

# Live check (manual):
python cli.py poll --predictor baseline

# Web page:
streamlit run app.py
6. Deploy (Streamlit Community Cloud, free)
1. Create a GitHub account and a new public repo (for example tradewatch).
2. Upload all files above. Add a .gitignore containing venv/, state.json, jev_cache.json, __pycache__/.
3. Go to share.streamlit.io, sign in with GitHub, click New app, pick the repo, set main file to app.py, then Deploy.
4. If using OpenJev: in the app's Settings > Secrets add
   TYPESAFE_API_KEY = "sk-codiv-xxxx"
   TYPESAFE_BASE_URL = "https://api.codiv.ai"
   Never put the key in the code or the repo.
5. Share the link. Tip: if the key is in Secrets, anyone using the page can spend your free tokens. Keep the default predictor as baseline, or share the link only with your reviewer.
7. Known simplifications (be upfront about these in your report)
• Entries and exits happen at the close price of the signal bar, with a flat 0.05% cost. Real trading has slippage (the price moving before your order fills).
• Long and short trades are compounded in one chain, a simplification.
• The latest bar in live mode may be unfinished (the hour is still in progress).
• Features are simple (returns, volatility, trend). A richer description of the market might help the AI.
• A few hundred bars give weak statistics. Treat results as a demo, not proof.
• OpenJev is a different model from TypeSafe's Jev, so results are not a verdict on the original.
8. How to explain it (a 2-minute script)
"TradeWatch is a test, not a trading bot. Before trusting an AI with money, I check two things on old data: is its confidence honest, and would acting on it have made money? I feed it hourly NIFTY data one bar at a time so it never sees the future. It gives chances for up, down or flat. I grade those chances with a report card called the Brier score. Then a strict rule only acts when the AI is very sure for several hours in a row, and uses a lower exit line and a rest period to avoid flip-flopping. Each paper trade becomes rupees. In my runs, the strict filter found no trades because the model's confidence wasn't trustworthy, which is the system working as designed."
9. Report template (fill in with your own numbers)
Title: TradeWatch: a shadow-test harness for AI market predictions
1. Objective. Test whether an AI's directional confidence is trustworthy before any capital is risked.
2. Method. Data source, date range, predictor used (baseline / OpenJev), horizon (3 hours), flat band (0.1%), filter settings.
3. Results. Accuracy vs 33% chance, Brier skill per class, number of trades, final capital vs start.
4. Findings. Was the model better than the lazy baseline? Did the filter allow trades? What happened when loosened?
5. Limitations. See section 7.
6. Next steps. Longer history, richer features, compare several models, more careful trade simulation.
7. Link and repo. Deployed URL and GitHub link.
10. If something breaks
• No data returned: check dates (hourly data covers only about 730 days) and that the end date is after the start date. Markets are closed on weekends.
• 401/403 from the model API: the key is missing or wrong.
• KeyError in _parse: print the raw response and adjust the parsing.
• Very slow jev runs: each hourly bar is one API call. 90 days is roughly 600 calls. Start with one week. The cache means a re-run is instant.
• Streamlit import error: run pip install -r requirements.txt again inside the virtual environment.
