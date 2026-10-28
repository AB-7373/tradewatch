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
