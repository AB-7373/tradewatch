# TradeWatch ⏱️📈

A **shadow-testing harness** to test whether an AI model's stock market predictions can be trusted before putting real money on the line.

TradeWatch replays historical hourly NIFTY 50 prices bar by bar (never letting the model see the future), asks an AI for direction probabilities, grades how honest those probabilities are via **Brier score calibration**, applies a strict institutional entry/exit state machine, and compounds simulated rupee returns.

---

## Key Features

1. **Zero Future Lookahead**: All technical features (rolling returns, volatility, trend vs. moving average) are calculated strictly on past and current bars.
2. **Probability Verification (Calibration)**: Grades predicted $P(\text{up}), P(\text{down}), P(\text{flat})$ against actual forward 3-hour outcomes. Computes multi-class accuracy, Brier scores, and Brier skill against a naive constant baseline.
3. **Institutional Execution State Machine**:
   - **Persistence Filter**: Requires confidence to clear a threshold (e.g. 85%) for several consecutive bars before entering.
   - **Hysteresis Exit**: Exits only when confidence falls below a lower threshold (e.g. 60%), preventing whipsaw.
   - **Cooldown**: Enforces a rest period after exiting before considering a new entry.
   - **Realistic Friction**: Deducts a 0.05% cost per round trip (brokerage & slippage).
4. **Dual Interfaces**: Full-featured CLI (`cli.py`), scenario comparison matrix (`compare.py`), and interactive Streamlit web dashboard (`app.py`).

---

## Project Structure

```
tradewatch/
├── config.py         # Global settings (ticker, flat band, horizon, API URLs)
├── data.py           # Hourly OHLC price fetcher via Yahoo Finance (yfinance)
├── features.py       # Past-only returns, volatility, and trend calculations
├── predictor.py      # Baseline formula predictor & OpenJev API client
├── calibration.py   # Ground-truth forward labels, Brier score, and skill calculations
├── signals.py        # Machine and Runner classes for stateful entry/exit rules
├── trades.py         # P&L compounding and fee deduction
├── pipeline.py       # Backtesting and incremental live polling coordinator
├── compare.py        # Scenario matrix runner (Strict, Medium, Loose vs Buy-and-Hold)
├── cli.py            # Command-line interface
├── app.py            # Streamlit web dashboard
├── requirements.txt  # Python package dependencies
└── context.md        # Detailed guide and reference documentation
```

---

## Installation & Setup

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/tradewatch.git
cd tradewatch

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate    # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

### Optional: Set OpenJev API Key
To test real AI predictions via OpenJev (hosted at [codiv.ai](https://codiv.ai)):
```bash
export TYPESAFE_BASE_URL="https://api.codiv.ai"
export TYPESAFE_API_KEY="sk-codiv-xxxx"
```
*(Without a key, the system defaults to the `baseline` formula predictor, which requires no external services.)*

---

## How to Run

### 1. Command Line Interface (CLI)

**Run an offline backtest with the Baseline Predictor:**
```bash
python cli.py analyze --start 2026-07-01 --end 2026-10-01 --predictor baseline
```

**Loosen filters to observe mechanics:**
```bash
python cli.py analyze --start 2026-07-01 --end 2026-10-01 --entry 0.55 --persist 2 --exit 0.45
```

**Run an OpenJev test (start with a 1-week range):**
```bash
python cli.py analyze --start 2026-10-01 --end 2026-10-08 --predictor jev
```

**Check live market bar incrementally:**
```bash
python cli.py poll --predictor baseline
```

---

### 2. Scenario Comparison Matrix

Run multiple rule presets (Strict, Medium, Loose) side-by-side against Buy-and-Hold:
```bash
python compare.py 2026-07-01 2026-10-01 baseline
```
This prints the comparison table and saves `comparison.csv`.

---

### 3. Streamlit Web Dashboard

Launch the interactive app:
```bash
streamlit run app.py
```

Features:
- Parameter sliders for entry, exit, streak length, and cooldown.
- Accuracy, total trades, and final rupee equity metrics.
- Calibration reliability charts for UP, DOWN, and FLAT classes.
- Historical price trajectory and individual trade logs.
- Manual live poll button.

---

## Deployment to Streamlit Community Cloud

1. Push this repository to GitHub (ensure `venv/`, `state.json`, and `jev_cache.json` are in `.gitignore`).
2. Go to [share.streamlit.io](https://share.streamlit.io) and create a **New app**.
3. Select your repository, set the branch to `main`, and the main file path to `app.py`.
4. In **Settings > Secrets**, add your API keys:
   ```toml
   TYPESAFE_API_KEY = "sk-codiv-xxxx"
   TYPESAFE_BASE_URL = "https://api.codiv.ai"
   ```
5. Deploy.

---

## Limitations & Simplifications

- **Simulated Execution**: Entries and exits execute at the bar close with a fixed 0.05% friction cost; live execution experiences slippage and spread variance.
- **Hourly Data Granularity**: Yahoo Finance provides approximately 730 days of hourly historical data.
- **Sample Size**: A few hundred bars produce initial observations rather than statistical proof. Results should be interpreted as an evaluation of forecast calibration rather than a guaranteed trading strategy.
