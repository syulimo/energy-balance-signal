# energy-balance-signal

![tests](https://github.com/syulimo/energy-balance-signal/actions/workflows/tests.yml/badge.svg) ![python](https://img.shields.io/badge/python-3.10%2B-blue) ![license](https://img.shields.io/badge/license-MIT-green)

> US crude and distillate weekly balances from EIA and CFTC data, an event study on WTI split by geopolitical regime, a walk-forward forecast of the weekly inventory print, a Hormuz reopening scenario tool, and a bridge from the benchmark crack to the refining margin per barrel that Valero reports, with a nowcast for the quarter in progress and a weekly note.

## Summary

- **What it is:** weekly US crude and distillate balances from 13 EIA series and CFTC positioning, aligned to release dates so no forecast uses data before it was public.
- **Real result so far:** the quarter-average Gulf Coast 3-2-1 crack forecasts Valero's reported refining margin with MAE 1.33 vs 2.24 $/bbl for last-quarter naive over 8 walk-forward quarters, direction right in 7 of 8; the bootstrap interval crosses zero, so this is suggestive (Section 4.2).
- **Not yet run on real data:** the crude and distillate event study and the weekly print forecast. The pipeline is validated on synthetic data with planted effects (Section 4.3) and runs live with a free EIA API key.

## 0. Why this repository exists now

This is not a textbook exercise on a calm market. As of mid-September 2026:

- The 2026 Iran war has kept the Strait of Hormuz severely constrained since late February. The IEA's September Oil Market Report puts 2026 world supply at 100.7 mb/d, down 5.7 mb/d year on year, and cuts 2026 demand by 2.5 mb/d, with the US-Iran diplomatic impasse and renewed attacks in the Gulf and at Bab el-Mandeb delaying normalisation (IEA OMR, 2026-09-11).
- Brent settled at 103.61 on 2026-09-17, up 13.8 percent in a month and 53.6 percent year on year. The EIA's September STEO expects Brent to average about $90 in 2H26 and fall to $74 in 2027 as inventories rebuild (EIA STEO, 2026-09-09).
- The tightest product is diesel, not crude. Gulf diesel net exports averaged 390 kb/d in August, about a quarter of pre-war levels; US distillate inventories are 13 percent below the five-year average and the EIA expects them to fall below 100 million barrels in September (IEA OMR 2026-09-11; EIA WPSR 2026-09-16; EIA STEO 2026-09-09).
- OPEC+ froze October quotas after a final 188 kb/d September increase completed the unwind of the 2023 cuts; about 2 mb/d of separate cuts remain through year end (OPEC+ statement, 2026-09-06).
- The weekly US print is itself noisy: for the week ending 2026-09-11, the API estimated a 7.1 mb build and the EIA reported a 0.6 mb draw.

In that environment the standard question, "does the Wednesday inventory surprise predict WTI," is incomplete. The questions this repository asks are the ones an energy desk analyst is asked in September 2026.

## 1. Questions

1. **Crude balance under regime change.** Did the EIA crude surprise carry information about forward WTI before the war, and does it still, or is it now drowned out by headline risk? The event study runs separately by regime (pre, war, partial reopening) using a dated events file.
2. **Distillate balance and the diesel crack.** Build the US distillate balance (production, imports, exports, product supplied), days of supply, deviation from the five-year average, and the NY Harbor diesel crack, and run the same event study on the distillate surprise.
3. **Is the weekly crude print forecastable?** Walk-forward ridge and gradient boosting on lagged flows against a naive trailing mean, with a paired bootstrap on the squared-error difference. "No" is an acceptable answer.
4. **What does reopening do to the balance?** A scenario tool stated relative to today, with IEA shut-in figures and two labelled assumptions, for 25 to 100 percent reopening over 3 to 9 months.
5. **From the commodity to the company.** A portfolio manager does not trade the diesel crack; they trade refiners. Does the quarter-average Gulf Coast 3-2-1 crack, known on the last day of the quarter, forecast the refining margin per barrel that Valero reports about four weeks later, better than assuming last quarter repeats? If it does, the quarter in progress can be nowcast every week.

## 2. Data

`data/SOURCES.md` lists every source with tier, cadence and fetch script. Nothing is committed except the hand-entered monthly balance table, the events file and the release calendar, each row of which carries its source and release date.

| tier | source | used for |
| --- | --- | --- |
| 1 | EIA WPSR via API v2 (13 weekly series) | crude and distillate balances, Cushing, SPR, utilization |
| 1 | CFTC COT disaggregated | managed money net length, WTI and ULSD |
| 1 | EIA daily spot (WTI, Brent, ULSD NYH, ULSD and gasoline Gulf Coast) | returns, diesel crack, Gulf Coast 3-2-1 crack |
| 1 | Valero Energy 8-K earnings releases, 10-Q and 10-K (SEC EDGAR) | reported refining margin per barrel of throughput, sixteen quarters in `data/refiner_margins.csv`, each row with its source url, release date and whether the figure is primary, secondary or derived |
| 2 | EIA STEO, IEA OMR, OPEC MOMR | monthly global balance, hand entered with release date |
| 3 | IEA, EIA, dated wire reporting | five dated events for the regime file |

`data/SOURCES.md` also records five measurement issues (API vs EIA, the EIA adjustment line, benchmark revisions, the 2026-09-23 format change, holiday release shifts) and how each is handled in code.

## 3. Method

**Balances.** `balance.py` and `distillate.py` compute implied weekly stock changes from flows, reported changes from stocks, and the EIA adjustment (reported minus implied). Weeks where the adjustment exceeds two standard deviations are flagged in the panel.

**Surprise.** Reported change minus a naive consensus proxy (trailing eight-week mean, lagged one week). Survey consensus is the upgrade; the proxy makes the result a floor.

**Regimes.** `regime.py` reads `data/events.csv` (five dated events, each with an IEA, EIA or dated wire source) and labels every week pre, war or partial. The label flips at each event, so the 2026-09-11 East-West pipeline shutdown returns the regime to war after the June partial reopening.

**Alignment.** `align.py` stamps EIA rows public at release (Wednesday t+5, or the date in `data/release_calendar.csv` after holidays) and COT rows at t+8, then merges as-of each Friday close, backward only. A test asserts that on Friday t the latest usable EIA week is t-7 and COT is t-14.

**Event study.** Quintile sort by signal, top minus bottom forward return at 1, 2, 4 weeks, bootstrap over weeks, run for all weeks, for each regime, and for every week since the first event (war and partial together). A group with fewer than 60 weeks is too short for quintiles and gets one OLS slope with a bootstrap interval instead; fewer than 20 weeks is reported as skipped.

**Forecast.** `forecast.py` builds lagged features (four lags of production, imports, exports, refinery inputs, utilization, Cushing), fits on a 156-week window, refits every 4 weeks, and compares ridge and gradient boosting to the naive trailing mean by RMSE with a paired bootstrap on the squared-error difference.

**Scenarios.** `scenario.py` takes the current Gulf shut-in from the IEA (9.4 mb/d below pre-war, IEA July 2026 OMR, June data), ramps a fraction of it back over 3, 6 or 9 months, subtracts an assumed demand recovery (0.25 mb/d per mb/d of supply, from the IEA's 2026 and 2027 demand swings) and an assumed unwind of US exports (0.10), and reports the incremental balance and cumulative stock change relative to today. Both assumptions are labelled ASSUMPTION in the config.

**Company layer.** `refiners.py` builds the Gulf Coast 3-2-1 crack against Brent from EIA daily spot prices, averages it by calendar quarter using only days on or before the forecast date, and fits an OLS per company, margin = a + b * crack, on quarters whose release date is on or before the last day of the target quarter. The benchmark is naive: the last margin the company had reported by that date. The score is mean absolute error, pooled and per company, with a paired bootstrap on the difference and the hit rate on the direction of the quarter-on-quarter change. `nowcast` applies the same fit to the quarter-to-date crack for the quarter in progress. A test poisons every margin released after the forecast date and asserts the forecast does not move.

**Weekly note.** `scripts/make_note.py` writes `notes/<week ending>.md` after each Wednesday release: reported, implied and adjustment for crude, the distillate balance and deviation from the five-year average, prices and the diesel crack, managed money positioning that was public on the note date, and the refiner nowcast. Two sections are left blank by design, "My read" and "What would change my mind". The code writes the numbers; the view is written by hand and committed. A note is written once and never regenerated.

## 4. Results

**4.1 Valero's reported margin, the series the company layer forecasts.** Sixteen quarters from SEC filings (`data/refiner_margins.csv`, source and status per row).

| quarter | USD/bbl | quarter | USD/bbl | quarter | USD/bbl | quarter | USD/bbl |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2022Q3 | 21.34 | 2023Q3 | 19.47 | 2024Q3 | 9.09 | 2025Q3 | 13.14 |
| 2022Q4 | 22.58 | 2023Q4 | 12.89 | 2024Q4 | 8.44 | 2025Q4 | 13.61 |
| 2023Q1 | 22.37 | 2024Q1 | 14.07 | 2025Q1 | 9.78 | 2026Q1 | 14.90 |
| 2023Q2 | 15.62 | 2024Q2 | 11.14 | 2025Q2 | 12.35 | 2026Q2 | 23.62 |

The bar the crack model has to beat is the naive forecast that last quarter repeats. Over the eight quarters the walk-forward scores (2024Q3 to 2026Q2, after eight training quarters), that naive forecast misses by 2.24 USD/bbl on average (absolute errors sum to 17.88 over 8 quarters), and by 8.72 in 2026Q2 alone, when the margin went from 14.90 to 23.62. A quarter like that is where a benchmark crack known on the last day of the quarter can help and last quarter's number cannot.

**4.2 Does the crack forecast the reported margin? Real data.** `python scripts/run_refiners.py --prices monthly` reproduces every number below from two committed files: `data/refiner_margins.csv` and `data/eia_spot_monthly.csv` (EIA monthly average spot prices for Brent, Gulf Coast ULSD and Gulf Coast gasoline). Outputs are committed in `results/*_monthly.*`.

In sample, over all sixteen quarters: margin = 2.20 + 0.59 * crack, R squared 0.87. A dollar of benchmark crack has been worth about 59 cents of reported margin, which is the capture an analyst would expect once product slate, crude differentials and secondary costs are counted.

Walk-forward, each forecast made on the last day of the quarter from quarters already reported:

| quarter | training quarters | crack | model | naive | reported | model error | naive error |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2024Q3 | 8 | 13.72 | 11.29 | 11.14 | 9.09 | 2.20 | 2.05 |
| 2024Q4 | 9 | 10.71 | 8.73 | 9.09 | 8.44 | 0.29 | 0.65 |
| 2025Q1 | 10 | 14.43 | 10.96 | 8.44 | 9.78 | 1.18 | 1.34 |
| 2025Q2 | 11 | 18.31 | 13.23 | 9.78 | 12.35 | 0.88 | 2.57 |
| 2025Q3 | 12 | 21.57 | 15.23 | 12.35 | 13.14 | 2.09 | 0.79 |
| 2025Q4 | 13 | 19.73 | 13.90 | 13.14 | 13.61 | 0.29 | 0.47 |
| 2026Q1 | 14 | 22.79 | 15.83 | 13.61 | 14.90 | 0.93 | 1.29 |
| 2026Q2 | 15 | 39.54 | 26.43 | 14.90 | 23.62 | 2.81 | 8.72 |

Mean absolute error 1.33 USD/bbl for the crack model against 2.24 for naive, a gain of 0.90. The bootstrap interval on that gain is [-0.25, +2.46]: with eight quarters it crosses zero, so this is suggestive, not conclusive. The model called the direction of the quarter-on-quarter change in seven of eight quarters. Most of the gain comes from 2026Q2, which is the point: the crack had already doubled by 30 June, a month before the release. The model also overshot that quarter by 2.81, which is what falling capture at very high cracks looks like.

Nowcast for 2026Q3 as of 31 August (July and August prices): the quarter-to-date crack is 61.58 USD/bbl, 56 percent above the highest quarter the model has seen (39.54). The linear fit gives 38.3 USD/bbl against 23.62 reported for Q2, and the code flags it as an extrapolation. Read with the Q2 overshoot, 38 is better treated as a ceiling than a point estimate; the defensible statement is that Q3 margin is set to rise well above Q2 unless September cracks collapse.

What a dollar is worth: at 2,950 kb/d, 92 days, a 21 percent tax rate and 294 million diluted shares (all from the Q2 2026 release), one USD/bbl of refining margin is about 0.73 USD of quarterly EPS before noncontrolling interests. That is the bridge from this nowcast to the number the market trades.

**4.3 Validation on synthetic data with planted effects** (`python scripts/demo_synthetic.py`, seeded, reproduces these numbers). The point is that the pipeline finds what is there and refuses what is not.

| check | planted | what the pipeline reports |
| --- | --- | --- |
| crude surprise, pre regime, 1 week | bearish effect | top minus bottom quintile +0.0423, interval [+0.0262, +0.0597], excludes zero |
| positioning, pre regime, 1 week | none | -0.0046, interval [-0.0187, +0.0097], crosses zero |
| every signal since the first event (25 weeks) | none | slopes with intervals that cross zero; too short for quintiles |
| next week's crude print | partly forecastable | RMSE naive 7,359 kb, ridge 5,238, gradient boosting 5,022; gain vs naive excludes zero |
| refiner margin, three synthetic companies | margin = a + 0.6 * crack | pooled MAE 0.67 vs naive 1.25 USD/bbl, gain +0.59, interval [+0.28, +1.01], direction hit rate 76 percent |
| refiner margin, no relationship | none | interval does not exclude zero (asserted in `tests/`) |
| Hormuz full reopening over three months | arithmetic | +6.1 mb/d incremental balance by month 12, about 2,000 mb cumulative, the same order as the more than 1 billion barrels the IEA says the crisis removed |

**4.4 Weekly balances and the event study.** These need thirteen weekly EIA series, daily spot prices and the CFTC history, which are fetched with a free EIA API key rather than redistributed. `scripts/run.py` writes `results/results.json` and the per-signal quantile tables, `scripts/run_refiners.py` reruns 4.2 on daily prices, and `scripts/make_note.py` records each week's numbers and the view taken on them in `notes/`.

## 5. Limitations

- **Sample split.** The war regime is 30 weeks old. Any regime-specific result is provisional. Below 60 weeks the code reports one slope with its interval instead of quintiles, and below 20 weeks it reports nothing.
- **Monthly prices in the committed run.** Section 4.2 uses EIA monthly averages weighted by business days. The crack is linear in prices, so the crack of monthly averages equals the monthly average of the daily crack; the only approximation is business days for trading days. With an API key the same script runs on daily prices.
- **Company layer, one company and small n.** Sixteen Valero quarters give eight scored quarters, so the interval will be wide and the band on the nowcast is indicative, not calibrated. One benchmark crack ignores regional mix, crude differentials, capture rate and outages; that residual is where an analyst's work starts. Refiners define margin per barrel differently, so a second company needs its own model and levels are never pooled.
- **Naive consensus.** Most of what the event study finds on real data will be the Wednesday reaction, not post-release drift. Survey consensus and daily prices with the 10:30 ET timestamp are the next step; the daily EIA spot series is already in the config.
- **Scenario assumptions.** Demand recovery and US export giveback are assumptions, not estimates. The tool is arithmetic with sources, useful for saying "if X then Y," not for predicting Y.
- **No roll, no costs.** Front-month spot returns ignore roll yield; a 2 percent four-week spread on a curve in backwardation is not what it looks like.
- **Hand-entered monthly table.** IEA and OPEC numbers are typed in from public summaries with release dates; the full OMR is paywalled.

## Weekly notes

`scripts/make_note.py` creates `notes/` and writes one file per EIA week, generated on the release day and completed by hand. The point is a dated record of views that can be checked later against what happened.

```bash
python scripts/fetch_eia.py && python scripts/fetch_cftc.py && python scripts/run_refiners.py && python scripts/make_note.py
```

## Try it without data

```bash
python scripts/demo_synthetic.py
```

Synthetic 2018 to 2026 panel with the real events file. Planted: a bearish crude-surprise effect in the pre-war regime only, no positioning effect, and a partly forecastable print. The event study finds the first in the pre regime and in all weeks, rejects positioning, and correctly skips the 13-week war and partial regimes; ridge and gradient boosting beat naive with intervals excluding zero. About thirty seconds. The demo then runs the company layer on a planted margin relationship and writes a sample note to `results/demo/note_demo.md`.

## Repository layout

```
src/energy_balance/
  balance.py       crude implied, reported, adjustment, surprise
  distillate.py    distillate balance, days of supply, five-year deviation, diesel crack
  positioning.py   managed money net, shifted rolling z-score
  regime.py        regime labels from data/events.csv
  align.py         release-date alignment with holiday calendar, backward as-of merge
  event_study.py   quintile sort, forward returns, bootstrap spread, bootstrap slope for short regimes
  forecast.py      lagged features, walk-forward ridge and gbm vs naive, paired bootstrap
  scenario.py      Hormuz reopening, incremental balance vs today
  refiners.py      Gulf Coast 3-2-1 crack, quarter averages as of a date, walk-forward vs naive, nowcast with extrapolation flag, monthly price path
  notes.py         weekly note: numbers generated, view left blank
  sources.py       EIA and CFTC parsers, unit tested without a network call
  pipeline.py      end to end
scripts/fetch_eia.py, fetch_cftc.py, run.py, run_refiners.py, make_note.py, demo_synthetic.py
configs/default.yaml           13 EIA series, 5 price series, the company layer and its EPS sensitivity inputs, windows, horizons, forecast spec, scenario inputs with sources
data/SOURCES.md                every source, tier, cadence, known measurement issues
data/events.csv                five dated regime events with source urls
data/global_balance_monthly.csv IEA, EIA STEO, OPEC numbers with release dates
data/release_calendar.csv      holiday release overrides
data/eia_spot_monthly.csv      EIA monthly average spot prices (Brent, Gulf Coast ULSD and gasoline), 2022-01 to 2026-08, committed with source urls
data/refiner_margins.csv       Valero reported refining margin per barrel, sixteen quarters, each with source url, release date and status
notes/                         created by make_note.py, one weekly note per EIA release
tests/                         25 tests: identities, past-only surprise, shifted z, no-lookahead alignment, holiday calendar, regime flips, walk-forward no-future, scenario monotonicity, planted-vs-null, EIA and CFTC parsers under both naming styles, crack units, quarter average as of a date, margins released after the forecast date cannot move it, planted crack relationship beats naive and a null does not, nowcast targets the quarter in progress, short-regime slope, weekly note content and publication lag, committed margins file sourced and contiguous, monthly prices expand to business-day weights, committed price file complete and checked against a hand calculation, extrapolation flag
```

## Run

```bash
pip install -e ".[dev]"
pytest
export EIA_API_KEY=...          # free at https://www.eia.gov/opendata/
python scripts/fetch_eia.py && python scripts/fetch_cftc.py
python scripts/run.py --config configs/default.yaml
python scripts/run_refiners.py --prices monthly                  # Valero backtest and nowcast, no key needed
python scripts/run_refiners.py                                   # same on daily EIA prices once fetched
python scripts/make_note.py                                       # after each Wednesday release
```

If a fetch fails, `python scripts/fetch_eia.py --check` pulls one series and prints the response, which is the fastest way to see what the API is returning.

## Design decisions

Recorded so the trade-offs are visible.

- Crude and distillate together rather than crude alone, because the September 2026 tightness is in middle distillates.
- Regime split from a dated events file rather than a statistical break test, because the breaks are known and sourced.
- Naive consensus proxy rather than survey data, to keep every input free and reproducible; the result is a floor.
- Forecast benchmarked against naive with a bootstrap, not reported as a standalone RMSE.
- Scenarios stated relative to today, because IEA annual averages already include the disruption and adding recovered flows to them double counts.
- A reported company KPI (refining margin per barrel) rather than a stock-price event study for the company layer, because the KPI is what an equity analyst forecasts before earnings and a price reaction mixes in everything else the market learned that day.
- A weekly note with the view left blank rather than an auto-generated commentary, because the numbers are the code's job and the judgment is the analyst's, and only a dated, hand-written view can be checked later.
- Markets matched on the CFTC contract code rather than the market name, because the WTI contract was renamed in 2022 and a name filter silently drops half the history.
- EIA monthly spot averages are committed so that the company layer produces real results for anyone who clones the repository, without an API key; the weekly layer still fetches its own data because thirteen weekly series and a positioning history do not belong in a repository.
