# TradeWatch: a shadow-test harness for AI market predictions

## 1. Objective

Test whether an AI model's directional confidence is trustworthy **before** any capital is risked. That means checking two separate things:

1. **Calibration.** When the model says 80%, does it happen about 80% of the time?
2. **Tradability.** Would a disciplined entry/exit rule built on that signal have made money after costs?

TradeWatch is a measuring instrument, not a trading bot. Every trade below is on paper.

## 2. Method

| | |
|---|---|
| Data | NIFTY 50 hourly bars from Yahoo Finance (`^NSEI`) |
| Predictors | **Baseline**: a one-line trend formula, free. **OpenJev** (`openjev-latest` via api.codiv.ai): an open-source server that copies the Jev API. |
| What the model sees | Past-only numbers: the 1h, 5h and 20h returns, 20-hour volatility, and the price versus its 20-hour average. No date and no index name. |
| Question | Over the next **3 hourly bars**, will the index rise by more than **0.1%**, fall by more than 0.1%, or stay flat in between? |
| Grading | Accuracy against the real class frequencies; Brier score per class; Brier skill against a lazy "always predict the average" forecaster (skill above 0 beats lazy) |
| Rules | Strict: enter ≥ 85% for 3 bars, exit < 60%, cooldown 3. Medium: 70% / 50% / 3 bars. Loose: 55% / 45% / 2 bars. Longs watch P(up) and shorts watch P(down). |
| Execution | Decide on bar *t*'s close and **fill at bar t+1's open**. Cost 0.05% per round trip. Start with ₹100,000, compounded. |
| Benchmark | Buy-and-hold over the same bars, with the same cost |

Backtest and live poll share one code path. An automated test checks that a run split into chunks gives exactly the same trades as one continuous run. 45 offline tests cover:

- the return maths;
- the state machine;
- the absence of lookahead;
- next-bar fills;
- state save and restore.

## 3. Results

### OpenJev: 17 Sep – 7 Oct 2026 (89 graded hours, 92 API calls)

| | Value |
|---|---|
| Accuracy | **39.3%** |
| Always guess "down" (the most common outcome) | 41.6% |
| What actually happened | up 35%, down 42%, flat 24% |
| What OpenJev rated most likely | up 11%, down 49%, flat 39% |
| Brier skill: up / down / flat | **−0.17 / −0.33 / −0.42** (all worse than lazy) |

Overconfidence was the clearest pattern:

- The 15 hours where it gave about 86% for "down": the price fell only 40% of the time.
- The 10 hours where it gave about 75% for "flat": the price stayed flat 20% of the time.

| Rules | Trades | Won | Return | Buy-and-hold |
|---|---|---|---|---|
| Strict | 2 | 0 | −0.26% | −3.02% |
| Medium | 3 | 1 | +0.15% | −3.02% |
| Loose | 6 | 3 | −0.28% | −3.02% |

For comparison, the **baseline on the same window** scored:

- accuracy 40.4%;
- skill −0.10 / −0.08 / −0.04;
- 0 trades at Strict and Medium, and 3 at Loose (−0.32%).

### Baseline: 13 Aug – 9 Nov 2026 (411 graded hours)

| | Value |
|---|---|
| Accuracy | **42.3%** |
| Always guess "up" | 41.1% |
| What actually happened | up 41%, down 39%, flat 20% |
| What the baseline rated most likely | up 45%, down 55%, flat **0%** (by design it never favours flat) |
| Brier skill: up / down / flat | **−0.06 / −0.09 / −0.06** (all worse than lazy) |

| Rules | Trades | Won | Return | Buy-and-hold |
|---|---|---|---|---|
| Strict | 0 | – | 0.00% | +2.79% |
| Medium | 1 | 1 | +7.27% | +2.79% |
| Loose | 14 | 5 | +7.96% | +2.79% |

The positive Medium and Loose numbers both come from **riding one rally**. NIFTY went from about 23,000 to 25,000 between 30 Oct and 9 Nov. Both trades were still open at the end and were marked at the last close:

- **Medium:** its only trade was a long opened on 2 Nov, worth +7.27%.
- **Loose:** a long opened on 30 Oct was worth **+₹8,921**. Without it, Loose's other 13 closed trades together lost about 1%.

That is luck, not skill.

### Earlier, pre-fix OpenJev run (kept for transparency, not comparable)

An earlier version sent "NIFTY 50 … As of 〈date〉" to the model, used a wrong short-return formula, and filled trades at the signal bar's own close. Over the same period (72 cached hours), OpenJev:

- scored 38.9% accuracy, against 47.2% for always guessing "down";
- had Brier skill of about −0.45 on every class;
- said "~95% down" 15 times, and was right 47% of the time.

The old comparison table showed Strict at 1 trade and +1.03%. That figure came from the bugs listed above and has been superseded.

## 4. Findings

- **No skill.** Neither predictor beat the lazy forecast on any outcome. Accuracy sits at or below "always guess the most common outcome". The usual "beats 33% random" comparison would have flattered both.
- **OpenJev is confidently wrong.** It often gives 85–95% probabilities, and those come true roughly as often as a coin flip. This is exactly the trap calibration checking exists to catch. Raw accuracy alone would not show it.
- **Removing the date and name did not rescue it.** Accuracy was about the same before and after the change, and calibration stayed far below lazy. So the earlier result was not an artefact of leaked dates. (The two samples differ slightly: 72 versus 89 hours.)
- **The filter behaved as designed.** At Strict settings the baseline never traded. OpenJev's two strict trades were small losses in a falling market.
- **Loosening the rules mostly adds noise.** The trades it adds are useful for checking the mechanics, not for judging the model. One well-timed trade can swing the whole result.

**Verdict:** the system correctly declines to trust either model's confidence. This matches the original concept note's finding with the real Jev.

## 5. Limitations

- **Small samples.** 89 hours for OpenJev and 411 for the baseline, with a handful of trades. These are observations, not statistical proof.
- **Costs.** One flat cost per trade. Real spread and slippage vary, especially at the open.
- **Overnight gaps.** NIFTY trades 9:15–15:30, and the last hourly bar is only 15 minutes long. Near the close, a 3-bar horizon spans an overnight gap.
- **The index is not tradable directly.** P&L assumes an instrument that tracks NIFTY 50 exactly and can be shorted freely.
- **One account.** Long and short trades are compounded in one chain.
- **Data depth.** Yahoo provides only about 730 days of hourly data.
- **OpenJev is not TypeSafe's Jev.** These results are not a verdict on the original model.

## 6. Next steps

- Grade OpenJev over a longer stretch (several months), within the API budget, and add confidence intervals (for example, a bootstrap) to the Brier skill.
- Try **recalibration**: learn a mapping from stated to real probabilities on one period, then test it on the next, a "walk-forward" test.
- Give the model a richer market description (volume, gaps, time of day), and compare several models on identical prompts.
- Model costs more carefully (spread at the open, a size-dependent cost), and size positions separately for long and short.

## 7. Links

- Live dashboard: _add your Streamlit link here_
- Code: _add your GitHub link here_

Reproduce every number above:

```bash
python compare.py 2026-08-11 2026-11-11 baseline
python compare.py 2026-09-14 2026-10-08 baseline jev    # uses bundled answers, no API calls
python cli.py analyze --start 2026-08-11 --end 2026-11-11
python cli.py analyze --start 2026-09-14 --end 2026-10-08 --predictor jev
```
