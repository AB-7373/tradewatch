"""TradeWatch dashboard.   Run with:  streamlit run app.py"""
import os
import streamlit as st

st.set_page_config(page_title="TradeWatch", layout="wide")


def _load_secrets():
    """On Streamlit Cloud, keys live in Settings > Secrets, never in the code.
    Optional JEV_PASSCODE: if set, the paid predictor only runs for people who know it."""
    try:
        for k in ("TYPESAFE_API_KEY", "TYPESAFE_BASE_URL", "JEV_MODEL"):
            if k in st.secrets:
                os.environ[k] = str(st.secrets[k])
        return str(st.secrets["JEV_PASSCODE"]) if "JEV_PASSCODE" in st.secrets else None
    except Exception:
        return None


PASSCODE = _load_secrets()

import datetime as dt                                   # noqa: E402  (after secrets on purpose)
import altair as alt                                    # noqa: E402
import pandas as pd                                     # noqa: E402
import config                                           # noqa: E402
from compare import PRESETS                             # noqa: E402
from data import MARKET_TZ, load_bars                   # noqa: E402
from features import add_features                       # noqa: E402
from pipeline import (build_predictor, equity_curve, poll_step,           # noqa: E402
                      run_analysis, summarize)
from signals import Cfg                                 # noqa: E402

INK, RUST, GREEN, MUTED, GRID = "#24446b", "#b04a32", "#2f7a55", "#8a8478", "#e7e3da"
JEV_WINDOW = (dt.date(2026, 9, 14), dt.date(2026, 10, 7))   # bars with bundled OpenJev answers
MAX_NEW_CALLS = 300

st.markdown("""
<style>
.block-container {padding-top: 2.2rem; max-width: 1180px;}
.stAppDeployButton {display: none;}
h1 {font-weight: 600; letter-spacing: -0.01em; margin-bottom: 0;}
.tw-lede {color: #55524b; font-size: 1.02rem; max-width: 760px; margin: 0.3rem 0 1.4rem 0;}
.tw-score {display: grid; grid-template-columns: repeat(5, 1fr); border-top: 1px solid #1c1c1a;
           border-bottom: 1px solid #dedad1; margin: 0.4rem 0 1.6rem 0;}
.tw-score > div {padding: 0.7rem 0.9rem 0.8rem 0; border-right: 1px solid #ece9e1;}
.tw-score > div:last-child {border-right: none;}
.tw-score .lbl {display: block; font-size: 0.72rem; text-transform: uppercase;
                letter-spacing: 0.06em; color: #6f6b62;}
.tw-score .val {display: block; font-family: "Source Serif Pro", "Source Serif 4", Georgia, serif;
                font-size: 1.75rem; line-height: 1.25; color: #1c1c1a;}
.tw-score .sub {display: block; font-size: 0.8rem; color: #6f6b62;}
.tw-verdict {border-left: 3px solid #24446b; padding: 0.2rem 0 0.2rem 1rem; margin: 0.6rem 0 1.2rem 0;}
.tw-verdict h3 {margin: 0 0 0.35rem 0; font-size: 1.35rem;}
.tw-verdict p {margin: 0 0 0.35rem 0; color: #33312c; max-width: 820px;}
.tw-note {color: #6f6b62; font-size: 0.88rem;}
@media (max-width: 800px) {.tw-score {grid-template-columns: repeat(2, 1fr);}}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------- helpers

def pct(x, signed=False):
    return "–" if x is None else (f"{x:+.2%}" if signed else f"{x:.1%}")


@st.cache_data(ttl=3600, show_spinner="Downloading hourly prices…")
def fetch_bars(start, end):
    return load_bars(start, end)


@st.cache_data(show_spinner="Replaying bars one at a time…", max_entries=50)
def backtest(bars, predictor, cfg_values, capital):
    cfg = Cfg(**cfg_values)
    r = run_analysis(None, None, predictor, cfg, capital, bars=bars)
    return r, summarize(r, cfg)


def naive_ist(idx):
    """Charts show market (IST) clock time no matter where the viewer is."""
    return pd.DatetimeIndex(idx).tz_convert(MARKET_TZ).tz_localize(None)


def verdict(s, cfg, who):
    acc, maj, mc = s["accuracy"], s["majority_accuracy"], s["majority_class"]
    beats = sum(v["skill"] > 0 for v in s["brier"].values())
    gap = acc - maj
    if beats == 0 and gap <= 0.02:
        head = "No evidence this model's confidence can be trusted"
    elif beats == 3 and gap > 0.02:
        head = "Some evidence of skill, worth a longer test"
    else:
        head = "Mixed evidence, not enough to trust it"
    cmp = "better than" if gap > 0.02 else ("about the same as" if gap >= -0.02 else "worse than")
    lines = [
        f"Over {s['bars_graded']} graded hours, {who} picked the right 3-hour outcome "
        f"{acc:.0%} of the time, {cmp} always guessing “{mc}” ({maj:.0%}).",
        f"Its probabilities beat a lazy “always guess the average” forecast on {beats} of 3 outcomes"
        + (", so its stated confidence is not honest." if beats == 0 else "."),
    ]
    n = s["trades"]
    if n == 0:
        lines.append(f"The rules never fired: the model was never at least {cfg.entry:.0%} sure for "
                     f"{cfg.persist} hours in a row. Declining to trade is the system working as intended.")
    else:
        lines.append(f"Trading on it took {n} paper trade{'s' if n != 1 else ''} ({s['wins']} won) and "
                     f"returned {pct(s['strategy_return'], True)}, against "
                     f"{pct(s['buy_and_hold_return'], True)} for buy-and-hold."
                     + (" That is far too few trades to mean anything on its own." if n < 10 else ""))
    body = "".join(f"<p>{x}</p>" for x in lines)
    st.markdown(f'<div class="tw-verdict"><h3>{head}</h3>{body}</div>', unsafe_allow_html=True)


def scorecard(s, cfg):
    skills = [v["skill"] for v in s["brier"].values()]
    cells = [
        ("Bars graded", f"{s['bars_graded']}", "hourly, 3-hour outcome"),
        ("Accuracy", pct(s["accuracy"]), f"always “{s['majority_class']}”: {pct(s['majority_accuracy'])}"),
        ("Brier skill", f"{sum(skills) / 3:+.2f}", "mean of up/down/flat; above 0 beats lazy"),
        ("Paper trades", f"{s['trades']}",
         f"{s['wins']} won" if s["trades"] else "filter declined"),
        ("Return", pct(s["strategy_return"], True), f"buy-and-hold {pct(s['buy_and_hold_return'], True)}"),
    ]
    html = "".join(f'<div><span class="lbl">{a}</span><span class="val">{b}</span>'
                   f'<span class="sub">{c}</span></div>' for a, b, c in cells)
    st.markdown(f'<div class="tw-score">{html}</div>', unsafe_allow_html=True)


def reliability_chart(cls, v):
    t = v["table"]
    diag = alt.Chart(pd.DataFrame({"x": [0, 1], "y": [0, 1]})).mark_line(
        strokeDash=[4, 4], color=MUTED, strokeWidth=1).encode(x="x:Q", y="y:Q")
    ax = dict(scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%", tickCount=5, gridColor=GRID))
    base = alt.Chart(t).encode(
        x=alt.X("avg_predicted:Q", title="Model said", **ax),
        y=alt.Y("actual_freq:Q", title="Actually happened", **ax))
    line = base.mark_line(color=INK, strokeWidth=1.4)
    dots = base.mark_circle(color=INK, opacity=0.9).encode(
        size=alt.Size("count:Q", scale=alt.Scale(range=[25, 420]), legend=None),
        tooltip=[alt.Tooltip("avg_predicted:Q", title="model said", format=".0%"),
                 alt.Tooltip("actual_freq:Q", title="happened", format=".0%"),
                 alt.Tooltip("count:Q", title="bars")])
    title = alt.TitleParams(cls.capitalize(), subtitle=f"Brier skill {v['skill']:+.2f}",
                            anchor="start", fontSize=15, subtitleColor="#6f6b62")
    return (diag + line + dots).properties(height=250, title=title)


def price_chart(feats, trades):
    px = pd.DataFrame({"time": naive_ist(feats.index), "close": feats["close"].values})
    line = alt.Chart(px).mark_line(color="#5d5a53", strokeWidth=1.1).encode(
        x=alt.X("time:T", title=None, axis=alt.Axis(format="%d %b", gridColor=GRID)),
        y=alt.Y("close:Q", title="NIFTY 50", scale=alt.Scale(zero=False),
                axis=alt.Axis(gridColor=GRID)),
        tooltip=[alt.Tooltip("time:T", format="%d %b %H:%M"), alt.Tooltip("close:Q", format=",.0f")])
    layers = [line]
    if trades:
        t = pd.DataFrame(trades)
        seg = pd.DataFrame({
            "t0": naive_ist(pd.to_datetime(t["entry_time"])), "p0": t["entry_price"],
            "t1": naive_ist(pd.to_datetime(t["exit_time"])), "p1": t["exit_price"],
            "side": t["side"], "ret": t["ret"], "status": t["status"]})
        color = alt.Color("side:N", scale=alt.Scale(domain=["long", "short"], range=[GREEN, RUST]),
                          legend=alt.Legend(title=None, orient="top"))
        tip = [alt.Tooltip("side:N"), alt.Tooltip("t0:T", title="entry", format="%d %b %H:%M"),
               alt.Tooltip("t1:T", title="exit", format="%d %b %H:%M"),
               alt.Tooltip("ret:Q", title="return", format="+.2%"), alt.Tooltip("status:N")]
        layers += [
            alt.Chart(seg).mark_rule(strokeWidth=2.5, opacity=0.8).encode(
                x="t0:T", x2="t1:T", y="p0:Q", y2="p1:Q", color=color, tooltip=tip),
            alt.Chart(seg).mark_point(filled=True, size=70).encode(
                x="t0:T", y="p0:Q", color=color, tooltip=tip,
                shape=alt.Shape("side:N", scale=alt.Scale(domain=["long", "short"],
                                range=["triangle-up", "triangle-down"]), legend=None)),
            alt.Chart(seg).mark_point(size=45, strokeWidth=1.5).encode(
                x="t1:T", y="p1:Q", color=color, tooltip=tip),
        ]
    return alt.layer(*layers).properties(height=300)


def equity_chart(r):
    feats, cap = r["feats"], r["start_capital"]
    times = naive_ist(feats.index)
    bh = pd.DataFrame({"time": times, "value": cap * feats["close"].values / feats["open"].iloc[0],
                       "line": "Buy and hold"})
    strat = pd.DataFrame({"time": times, "line": "Strategy (paper)",
                          "value": equity_curve(feats, r["trades"], cap).values})
    df = pd.concat([bh, strat])
    return alt.Chart(df).mark_line(strokeWidth=1.6).encode(
        x=alt.X("time:T", title=None, axis=alt.Axis(format="%d %b", gridColor=GRID)),
        y=alt.Y("value:Q", title="Account (₹)", scale=alt.Scale(zero=False),
                axis=alt.Axis(format=",.0f", gridColor=GRID)),
        color=alt.Color("line:N", scale=alt.Scale(domain=["Strategy (paper)", "Buy and hold"],
                        range=[INK, "#b9b4a8"]), legend=alt.Legend(title=None, orient="top")),
        tooltip=[alt.Tooltip("line:N", title=""), alt.Tooltip("time:T", format="%d %b %H:%M"),
                 alt.Tooltip("value:Q", format=",.0f")],
    ).properties(height=220)


def trade_table(trades):
    t = pd.DataFrame(trades)
    fmt = lambda s: pd.to_datetime(s).dt.tz_convert(MARKET_TZ).dt.strftime("%d %b %H:%M")
    out = pd.DataFrame({
        "Side": t["side"].str.capitalize(),
        "Signal": fmt(t["signal_time"]),
        "Entry": fmt(t["entry_time"]), "Entry price": t["entry_price"],
        "Exit": fmt(t["exit_time"]), "Exit price": t["exit_price"],
        "Return": t["ret"] * 100, "P&L (₹)": t["pnl"], "Status": t["status"].str.capitalize(),
    })
    st.dataframe(out, hide_index=True, width="stretch", column_config={
        "Entry price": st.column_config.NumberColumn(format="%.1f"),
        "Exit price": st.column_config.NumberColumn(format="%.1f"),
        "Return": st.column_config.NumberColumn(format="%+.2f%%"),
        "P&L (₹)": st.column_config.NumberColumn(format="%+,.0f"),
    })


# ---------------------------------------------------------------- sidebar

ss = st.session_state
today = pd.Timestamp.now(tz=MARKET_TZ).date()
ss.setdefault("start", today - dt.timedelta(days=90))
ss.setdefault("end", today)
for k, v in next(iter(PRESETS.values())).items():
    ss.setdefault(k, v)


def apply_preset():
    if ss.preset in PRESETS:
        for k, v in PRESETS[ss.preset].items():
            ss[k] = v


def use_jev_window():
    ss.start, ss.end = JEV_WINDOW


with st.sidebar:
    st.markdown("#### Data")
    predictor = st.radio("Predictor", ["baseline", "jev"], horizontal=True,
                         format_func={"baseline": "Baseline formula", "jev": "OpenJev"}.get,
                         help="Baseline: a one-line trend formula, free. OpenJev: an AI model "
                              "via api.codiv.ai (each new hour is one API call).")
    c1, c2 = st.columns(2)
    start = c1.date_input("From", key="start", min_value=today - dt.timedelta(days=725), max_value=today)
    end = c2.date_input("To", key="end", min_value=today - dt.timedelta(days=725), max_value=today)
    if predictor == "jev":
        st.button("Use the bundled OpenJev window", on_click=use_jev_window,
                  help=f"{JEV_WINDOW[0]:%d %b} – {JEV_WINDOW[1]:%d %b %Y}: answers are saved, no API calls.")
    capital = st.number_input("Starting capital (₹)", value=100000.0, step=10000.0, format="%.0f")

    st.markdown("#### Rules")
    st.selectbox("Preset", list(PRESETS) + ["Custom"], key="preset", on_change=apply_preset)
    st.slider("Enter when confidence ≥", 0.50, 0.99, key="entry", step=0.01)
    st.slider("Exit when confidence <", 0.30, 0.95, key="exit", step=0.01)
    st.slider("…for this many hours in a row", 1, 8, key="persist")
    st.slider("Cooldown after exit (hours)", 0, 8, key="cooldown")
    cost_pct = st.number_input("Cost per round trip (%)", value=0.05, min_value=0.0, max_value=1.0,
                               step=0.01, format="%.2f", help="Brokerage and slippage, paid once per trade.")

    can_spend = False
    if predictor == "jev" and config.API_KEY:
        if PASSCODE is None:
            can_spend = True
        else:
            can_spend = st.text_input("Passcode for new API calls", type="password") == PASSCODE

# ---------------------------------------------------------------- page

st.title("TradeWatch")
st.markdown('<p class="tw-lede">A shadow test for AI market predictions. It replays hourly NIFTY 50 '
            'prices one bar at a time, asks a model how likely the next three hours are to go up, down '
            'or stay flat, grades those odds against what really happened, and paper-trades them '
            'under strict entry and exit rules. No real orders are ever placed.</p>',
            unsafe_allow_html=True)

try:
    cfg = Cfg(entry=ss.entry, exit=ss.exit, persist=ss.persist, cooldown=ss.cooldown,
              cost=cost_pct / 100)
except ValueError as e:
    st.error(str(e))
    st.stop()

tab_bt, tab_live, tab_how = st.tabs(["Backtest", "Live check", "How it works"])

with tab_bt:
    if start >= end:
        st.error("“From” must be before “To”.")
        st.stop()
    try:
        bars, source = fetch_bars(str(start), str(end + dt.timedelta(days=1)))
    except RuntimeError as e:
        st.error(str(e))
        st.stop()
    if source == "sample":
        st.markdown(f'<p class="tw-note">Yahoo Finance did not respond, so this uses the price sample '
                    f'bundled with the app ({bars.index[0]:%d %b %Y} – {bars.index[-1]:%d %b %Y}).</p>',
                    unsafe_allow_html=True)
    if len(bars) < 30:
        st.error("Not enough hourly bars in this range. Pick at least a week of trading days.")
        st.stop()

    if predictor == "jev":
        need = build_predictor("jev").missing(add_features(bars))
        if need and not can_spend:
            st.info(f"OpenJev has not been asked about {need} of the hours in this range, and this "
                    f"copy of the app is not allowed to spend API calls. Use the bundled window "
                    f"({JEV_WINDOW[0]:%d %b} – {JEV_WINDOW[1]:%d %b %Y}) from the sidebar.")
            st.stop()
        if need > MAX_NEW_CALLS:
            st.warning(f"This range needs {need} new API calls. Please pick a shorter range "
                       f"(at most {MAX_NEW_CALLS}).")
            st.stop()
        if need and not st.checkbox(f"Allow {need} new OpenJev API calls (uses free-tier tokens)"):
            st.stop()

    try:
        r, s = backtest(bars, predictor, cfg.__dict__, capital)
    except Exception as e:                                  # API errors, parsing errors
        st.error(f"The run failed: {e}")
        st.stop()

    who = "the baseline formula" if predictor == "baseline" else "OpenJev"
    verdict(s, cfg, who)
    scorecard(s, cfg)

    st.subheader("1. Is the model's confidence honest?")
    st.markdown('<p class="tw-note">Hours are grouped by the probability the model gave. If its '
                'confidence were honest, the dots would sit on the dashed line: when it says 70%, '
                'that outcome happens about 70% of the time. Bigger dots mean more hours.</p>',
                unsafe_allow_html=True)
    cols = st.columns(3)
    for col, (cls, v) in zip(cols, r["report"]["classes"].items()):
        col.altair_chart(reliability_chart(cls, v), width="stretch")
    freq = ", ".join(f"{c} {v:.0%}" for c, v in s["class_freq"].items())
    picked = ", ".join(f"{c} {v:.0%}" for c, v in s["picked_freq"].items())
    st.markdown(f'<p class="tw-note">What actually happened: {freq}. '
                f'What the model rated most likely: {picked}.</p>', unsafe_allow_html=True)

    st.subheader("2. Would trading on it have paid?")
    st.markdown(f'<p class="tw-note">Long when P(up) stays at or above {cfg.entry:.0%} for {cfg.persist} '
                f'hours in a row, short on the same rule for P(down); exit when it drops below '
                f'{cfg.exit:.0%}, then wait {cfg.cooldown} hours. Orders fill at the next hour\'s open, '
                f'minus {cfg.cost:.2%} per round trip.</p>', unsafe_allow_html=True)
    st.altair_chart(price_chart(r["feats"], r["trades"]), width="stretch")
    st.altair_chart(equity_chart(r), width="stretch")

    if r["trades"]:
        trade_table(r["trades"])
    else:
        st.markdown('<p class="tw-note">No trades. The filter refused to act on this signal.</p>',
                    unsafe_allow_html=True)
    if s["pending_orders"]:
        st.markdown(f'<p class="tw-note">A signal on the last hour has not been filled yet '
                    f'(no next bar): {s["pending_orders"]}.</p>', unsafe_allow_html=True)

with tab_live:
    st.markdown("Checks for hourly bars that have **finished** since your last check, runs them "
                "through exactly the same rules as the backtest, and remembers any open position. "
                "Nothing runs on a schedule: a check only happens when you press the button.")
    st.markdown('<p class="tw-note">Your position is remembered for this browser session only. '
                'The command line version (<code>python cli.py poll</code>) saves it to state.json.</p>',
                unsafe_allow_html=True)
    live_pred = predictor if (predictor == "baseline" or can_spend) else "baseline"
    if live_pred != predictor:
        st.markdown('<p class="tw-note">Live checks use the baseline formula here, because new OpenJev '
                    'calls are not enabled for this copy of the app.</p>', unsafe_allow_html=True)
    b1, b2, _ = st.columns([1, 1, 4])
    if b1.button("Check for new bars", type="primary"):
        try:
            ss.poll_out = poll_step(ss.get("poll_state"), live_pred, cfg)
            ss.poll_state = ss.poll_out["state"]
        except Exception as e:
            st.error(f"Live check failed: {e}")
    if b2.button("Reset"):
        ss.pop("poll_state", None)
        ss.pop("poll_out", None)
    out = ss.get("poll_out")
    if out:
        last = pd.Timestamp(out["last_bar"]).tz_convert(MARKET_TZ) if out["last_bar"] else None
        st.markdown(f"**{out['new_bars']} new bar{'s' if out['new_bars'] != 1 else ''}** processed. "
                    f"Latest finished bar: {last:%a %d %b, %H:%M} IST." if last else "No bars yet.")
        if "last_probs" in out:
            p = out["last_probs"]
            st.markdown(f"Model's latest odds for the next 3 hours: up **{p['p_up']:.0%}**, "
                        f"down **{p['p_down']:.0%}**, flat **{p['p_flat']:.0%}**.")
        state = out["state"]
        m = state["machines"]
        st.markdown(f'<p class="tw-note">Long: {"in a position" if m["long"]["in_pos"] else "flat"}, '
                    f'streak {m["long"]["streak"]}/{cfg.persist}. Short: '
                    f'{"in a position" if m["short"]["in_pos"] else "flat"}, streak '
                    f'{m["short"]["streak"]}/{cfg.persist}.</p>', unsafe_allow_html=True)
        if out["positions"]:
            trade_table([{**t, "pnl": capital * t["ret"]} for t in out["positions"]])

with tab_how:
    st.markdown("""
#### The question
Before trusting an AI with money, check two things on past data: **is its confidence honest**, and
**would acting on it have made money**? TradeWatch is a measuring instrument for both. It is not a
trading bot.

#### How a run works
1. **Prices.** Hourly NIFTY 50 bars from Yahoo Finance (about the last two years are available).
2. **What the model sees.** Only past numbers: the last 1, 5 and 20 hour returns, recent volatility,
   and how far the price is from its 20-hour average. No dates and no index name, so a language model
   cannot recall what happened next from news it may have read.
3. **The question asked.** Over the next 3 hours, will the index rise more than 0.1%, fall more than
   0.1%, or stay in between? The model answers with three probabilities.
4. **Grading.** The **Brier score** is a report card for probabilities (lower is better). It is
   compared with a lazy forecaster who always says the average. **Skill above 0** means better than lazy.
5. **Rules.** Enter only after the probability stays high for several hours in a row (the
   *persistence filter*). Exit only when it falls clearly lower (*hysteresis*). Then rest
   (*cooldown*). Longs watch P(up), shorts watch P(down).
6. **Money.** Each decision is filled at the **next** hour's opening price, minus a cost, and trades
   are compounded in rupees.

#### Being honest about the limits
- A few hundred hours and a handful of trades are a demonstration, not proof.
- One flat cost per trade. Real orders also face spread and slippage.
- NIFTY itself cannot be bought directly. The P&L assumes an instrument that tracks it and can be
  shorted freely. Long and short trades share one compounded account.
- Near the 3:30 pm close, the next three hours include an overnight gap.
- OpenJev is an open-source model that copies the Jev API. It is not TypeSafe's Jev, so these
  results say nothing about the original.
""")
