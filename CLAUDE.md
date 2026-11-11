# TradeWatch — instructions for Claude Code

## About this project
TradeWatch is a shadow-testing harness (paper trading only, never real orders). It replays hourly NIFTY 50 bars one at a time, asks a predictor (`baseline` formula, or `jev` = OpenJev via api.codiv.ai) for P(up)/P(down)/P(flat) over the next 3 bars, grades those probabilities (accuracy, Brier score, Brier skill vs. a "lazy" baseline), runs an entry/exit state machine (persistence filter, hysteresis exit, cooldown) for long and short, and compounds paper P&L in rupees. Interfaces: `cli.py`, `compare.py`, `app.py` (Streamlit). `context.md` is the original build guide.

Goal: make it correct, honest, tested, and polished enough to demo and present (deployed Streamlit link + GitHub repo + short written report).

## About the user
- Beginner at coding. Explain what you change and why in plain, friendly language; explain any jargon once in simple words.
- Runs Pop!_OS (Linux), VS Code, Python venv in `venv/`.
- Work in small steps. Before starting, make sure the folder is a git repo (`git init` + initial commit if not). Commit after each completed task with a clear message so anything can be undone.

## Hard rules
- The `jev` predictor spends limited free API tokens. User has allowed using it *when needed* (e.g. one small post-fix run for the report) — never for routine testing. Use `--predictor baseline` for all testing.
- Never put API keys in code or commit them. Keep `venv/`, `state.json`, `jev_cache.json`, `__pycache__/`, `.env` in `.gitignore`.
- Preserve the core design: backtest and live poll must share the same `Runner` code path.

## Task list (do in order)

### Phase 1 — Correctness bugs
1. **Short return formula** (`trades.py`, `close_trade`): currently `entry / price - 1` for shorts, which is wrong (overstates wins, understates losses). Must be `1 - price / entry`.
2. **Date leak to the AI** (`features.py`, `describe`): remove the timestamp ("As of {ts}") and the "NIFTY 50" name from the text sent to the model. An LLM may have seen news about that period, which leaks the future. Send only the numeric features (e.g. "An equity index, hourly bars: ...").
3. **Cache key** (`predictor.py`, `JevPredictor.predict`): include a hash (e.g. md5) of the state text in the cache key, so changing the prompt doesn't reuse stale answers. Keep timestamp in the key too if helpful.
4. **Unfinished bar in live poll** (`pipeline.py`, `poll`): drop any bar whose hour hasn't finished yet (bar start + 1h > now, timezone-aware, Asia/Kolkata) before processing, so a half-finished bar is never consumed and skipped forever.
5. **Same-bar execution lookahead**: signals use bar t's close, so filling at bar t's close is unrealistic. Change entries and exits to fill at the **next bar's open**. This means keeping `Open` in the features frame and passing it through `Runner.process`. If a signal happens on the last bar, there is no next bar: leave it pending/unfilled. Make sure backtest and poll both behave the same. Mark still-open trades at the last close as before.

### Phase 2 — Honest reporting
6. In `calibration_report`, add actual class frequencies (how often up/down/flat really happened) and "majority-class accuracy" (always guess the most common outcome). Show these in the CLI and dashboard next to model accuracy, because "random = 33%" is misleading when classes are unbalanced.
7. Add a `--cost` CLI option and a dashboard input (default 0.0005), and pass it into `Cfg`.
8. Make sure `compare.py` exists and works (Strict / Medium / Loose presets vs. Buy-and-Hold). Buy-and-hold should use the same cost assumption.
9. Update README: replace "institutional" wording with plain "entry/exit state machine"; update Limitations to cover: next-bar-open fills, flat cost, overnight gaps (a 3-bar horizon near close spans overnight), NIFTY index can't be traded directly (P&L assumes a hypothetical instrument you can go long/short freely), long+short compounded in one chain, small sample size, OpenJev ≠ TypeSafe's Jev.

### Phase 3 — Tests and verification
10. Add `pytest` to requirements and a `tests/` folder with tests that need no network:
    - short and long return math (including the 100 → 200 short = −100% case) and cost deduction
    - `Machine` transitions: persistence (enters only after N consecutive bars ≥ entry), hysteresis exit, cooldown blocks re-entry
    - no-lookahead: features at time t are identical whether or not future bars are appended
    - `make_labels` produces up/down/flat correctly and NaN at the end
    - next-bar-open fill behaviour
    - `Runner` state round-trips through `to_dict()` / restore
11. Run `pytest`, then run end-to-end with real data:
    `python cli.py analyze --start <~3 months ago> --end <today> --predictor baseline`
    plus a loosened run (`--entry 0.55 --persist 2 --exit 0.45`) and `python compare.py ...`. Remember Yahoo hourly data only goes back ~730 days.
12. Run `streamlit run app.py` and check that the dashboard loads and a baseline backtest works. Report any errors and fix them.

### Phase 4 — Ship it
13. Pin versions in `requirements.txt` (use what's installed and working).
14. Help the user create a GitHub repo and push (they may need guidance on logging in with `gh auth login` or SSH).
15. Walk the user through deploying on Streamlit Community Cloud (share.streamlit.io) with `app.py`; keys only in Secrets; default predictor stays `baseline`.
16. Write `REPORT.md` using the template in `context.md` section 9, filled in with the REAL numbers from the baseline runs (and Jev runs only if the user ran them). Keep it honest: "the filter refused to trade" is a valid result.

### Amendments (from review, 2026-11-11)
- Set up pytest first (task 0) and write each bug's test together with its fix.
- Task 5: implement as "pending orders" inside `Runner` (fill at the next bar's open; pending orders saved in `to_dict()`). Task 4: comment that NIFTY's 15:15 bar is only 15 min long.
- 5b: validate exit < entry in `Cfg`, CLI and dashboard.
- Add `--json` to `cli.py analyze` (the brief's "JSON API" — deliberately no server).
- Extra tests: chunked Runner run == continuous run; `describe()` has no date / "NIFTY".
- Free check: does cached OpenJev agree with the baseline's direction (both showed 39.3% accuracy)?
- Dashboard: cache data downloads, friendly Yahoo error, bundled sample-CSV fallback, reliability chart with diagonal, warn that poll state is shared on cloud, Jev disabled when no key is set.
- **Redesign the dashboard so it looks hand-made rather than template/AI-generated** (restrained palette, no emoji clutter, clear story: verdict → calibration → trades).
- Old Jev numbers in comparison.csv are pre-fix; label them so in REPORT.md.

### Status (2026-11-11)
Tasks 0–14, 16 and all amendments are done and pushed to github.com/AB-7373/tradewatch. 45 offline tests pass. One post-fix OpenJev run was made (92 calls, window 14 Sep – 8 Oct 2026); those answers are bundled in `sample_data/jev_answers.json`.
Remaining: task 15. The user deploys on share.streamlit.io, then pastes the live link into README.md ("Live demo") and REPORT.md section 7.

When everything is done, give the user a short plain-language summary of what changed and how to demo it in 2 minutes.
