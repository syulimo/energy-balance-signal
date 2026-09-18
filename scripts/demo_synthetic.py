"""Synthetic demo of the whole pipeline: crude and distillate balances, regimes from
data/events.csv, event study by regime, walk-forward forecast vs naive, Hormuz scenarios.
Then the company layer (benchmark crack to reported refining margin, walk-forward against
naive, nowcast for the quarter in progress) and a sample weekly note.
No API key, no data. About thirty seconds.

Planted: crude surprise has a bearish effect on next-week WTI in the pre-war regime
only (it is drowned out after 2026-02-28); positioning has no effect; next week's
crude print is partly forecastable from lagged refinery inputs.
"""
import json, numpy as np, pandas as pd, yaml
from energy_balance.pipeline import run

rng = np.random.default_rng(3)
weeks = pd.date_range("2018-01-05", periods=452, freq="W-FRI")   # runs into late 2026
n = len(weeks); war = weeks >= pd.Timestamp("2026-02-28")
ref = 16500 + 800 * np.sin(np.arange(n) * 2 * np.pi / 52) + rng.normal(0, 200, n)
prod = 12000 + np.cumsum(rng.normal(0, 25, n)); imp = 6500 + rng.normal(0, 300, n) - 800 * war
exp_ = 3800 + np.cumsum(rng.normal(0, 15, n)) + 1200 * war
implied = (prod + imp - exp_ - ref) * 7
reported = implied - 0.6 * (ref - 16500) * 7 * 0.2 + rng.normal(0, 2500, n)    # lagged refinery effect makes the print partly forecastable
reported = reported + np.roll(-0.4 * (ref - 16500) * 7 * 0.3, 1)
stocks = 440000 + np.cumsum(reported)
d_prod = 5100 + rng.normal(0, 120, n); d_imp = 150 + rng.normal(0, 40, n); d_exp = 1300 + rng.normal(0, 100, n) + 300 * war
d_sup = 3900 + 200 * np.sin(np.arange(n) * 2 * np.pi / 52) + rng.normal(0, 120, n)
d_stocks = 120000 + np.cumsum((d_prod + d_imp - d_exp - d_sup) * 7 + rng.normal(0, 1500, n))
eia = pd.DataFrame({"crude_stocks_ex_spr": stocks, "crude_stocks_cushing": 25000 + rng.normal(0, 800, n), "crude_production": prod,
                    "crude_imports": imp, "crude_exports": exp_, "refinery_inputs": ref, "refinery_utilization": 90 + rng.normal(0, 2, n),
                    "distillate_stocks": d_stocks, "distillate_production": d_prod, "distillate_imports": d_imp,
                    "distillate_exports": d_exp, "distillate_product_supplied": d_sup}, index=weeks)
cot = pd.DataFrame({"mm_long": 300000 + np.cumsum(rng.normal(0, 8000, n)), "mm_short": 80000 + np.cumsum(rng.normal(0, 4000, n)),
                    "open_interest": 2.0e6 + rng.normal(0, 50000, n)}, index=weeks)
surprise = reported - pd.Series(reported).shift(1).rolling(8).mean().fillna(0).to_numpy()
ret = rng.normal(0, 0.04, n) + 0.10 * war * rng.normal(0, 0.06, n)                 # war regime is noisier
ret = ret - 0.015 * (surprise / 5000) * (~war)                                       # planted effect pre-war only
ret = np.roll(ret, 2)
close = 55 * np.cumprod(1 + ret); close[war] *= 1.3
ulsd = close / 42 + 0.6 + 0.9 * war + rng.normal(0, 0.05, n)                         # crack widens in war
price = pd.DataFrame({"close": close, "ulsd": ulsd}, index=weeks)

cfg = yaml.safe_load(open("configs/default.yaml")); cfg["output"]["dir"] = "results/demo"
cfg["forecast"]["train_window_weeks"] = 104; cfg["forecast"]["bootstrap_draws"] = 300; cfg["event_study"]["bootstrap_draws"] = 300
res = run(eia, cot, price, cfg)

def fmt(r):
    k = "spread" if "spread" in r else "slope"
    return f"{k} {r[k]:+.4f} CI [{r['ci_low']:+.4f}, {r['ci_high']:+.4f}] {'excludes zero' if r['ci_low']>0 or r['ci_high']<0 else 'crosses zero'}" + (f" (n={r['n']}, slope because the regime is short)" if k == "slope" else "")
print(f"usable weeks {res['n_weeks']}, adjustment flags {res['adjustment_flags']}\n")
print("EVENT STUDY, 1-week horizon, by regime (planted: crude surprise bearish pre-war only)")
for g, d in res["event_study"].items():
    for sname, r in d.items():
        print(f"  {g:8s} {sname:22s} {fmt(r['fwd_1w']) if 'fwd_1w' in r else r['skipped']}")
print("\nFORECAST next-week crude print vs naive (planted: partly forecastable from refinery inputs)")
for m, r in res["forecast"].items():
    print(f"  {m:6s} rmse {r['rmse']:8.0f} kb   gain vs naive {r['mse_gain_vs_naive']:+10.0f} CI [{r['ci_low']:+.0f}, {r['ci_high']:+.0f}]")
print("\nHORMUZ SCENARIOS, incremental vs today (IEA shut-in + two labelled assumptions)")
sc = pd.DataFrame(res["scenario"])
print(sc[["reopening_fraction", "months_to_full", "supply_back_m12_mbd", "incremental_balance_m12_mbd", "cum_stock_change_vs_today_12m_mb"]].to_string(index=False))

# company layer: planted margin = a_i + 0.6 * quarter-average crack + noise, released 27 days after quarter end
from pathlib import Path
from energy_balance.refiners import benchmark_crack, load_margins, nowcast, quarter_average, score, walk_forward
from energy_balance.notes import build_note
from energy_balance.pipeline import eia_features
days = pd.date_range("2021-01-01", weeks[-1] + pd.Timedelta(days=5), freq="B"); m = len(days); dwar = days >= pd.Timestamp("2026-02-28")
brent = 70 + np.cumsum(rng.normal(0, 0.8, m)) + 25 * dwar
gas = brent / 42 + 0.35 + rng.normal(0, 0.03, m) + 0.10 * dwar; dist = brent / 42 + 0.55 + np.cumsum(rng.normal(0, 0.004, m)) + 0.70 * dwar
daily = pd.DataFrame({"wti_cushing": brent - 4, "brent": brent, "ulsd_nyh": dist + 0.03, "ulsd_usgc": dist, "gasoline_usgc": gas}, index=days)
crack = benchmark_crack(daily, cfg["refiners"]["benchmark"]); q = quarter_average(crack); rows = []
for tkr, a in {"SYN_A": 1.5, "SYN_B": 4.0, "SYN_C": -1.0}.items():
    for per, r in q[q["complete"]].iterrows():
        rows.append({"ticker": tkr, "fiscal_quarter": str(per), "period_end": per.end_time.date(), "release_date": (per.end_time + pd.Timedelta(days=27)).date(),
                     "metric": "synthetic", "value_usd_bbl": round(a + 0.6 * r["crack"] + rng.normal(0, 0.8), 2), "source_url": "synthetic"})
mpath = Path("results/demo/refiner_margins_synthetic.csv"); pd.DataFrame(rows).to_csv(mpath, index=False)
margins = load_margins(str(mpath)); bt = walk_forward(margins, crack, cfg["refiners"]["min_train_quarters"]); sc = score(bt, 300)
nc = nowcast(margins, crack, days[-1], cfg["refiners"]["min_train_quarters"], bt)
print("\nREFINER MARGIN, walk-forward vs naive last quarter (planted: margin = a_i + 0.6 * crack)")
for k, r in sc.items():
    print(f"  {k:6s} n {r['n']:3d}  MAE model {r['mae_model']:.2f}  naive {r['mae_naive']:.2f}  gain {r['mae_gain_vs_naive']:+.2f} CI [{r['ci_low']:+.2f}, {r['ci_high']:+.2f}]  direction hit {r['direction_hit_rate']:.0%}")
print("\nNOWCAST, quarter in progress"); print(nc[["ticker", "quarter", "days_in_quarter_so_far", "crack", "pred", "band_low", "band_high", "naive"]].round(2).to_string(index=False))
note = build_note(eia_features(eia, cfg), cot, daily, cfg, "war", None, nc)
Path("results/demo/note_demo.md").write_text(note)
print("\nwritten to results/demo/ (including note_demo.md)")
