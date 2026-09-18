"""Valero margin backtest and current-quarter nowcast.
  python scripts/run_refiners.py                    # daily EIA prices if data/prices_daily.csv exists, else the committed monthly file
  python scripts/run_refiners.py --prices monthly   # force the committed monthly averages (no API key needed)
"""
import argparse, json, yaml, pandas as pd
from pathlib import Path
from energy_balance.refiners import benchmark_crack, expand_monthly, full_sample_fit, load_margins, nowcast, score, walk_forward

ap = argparse.ArgumentParser(); ap.add_argument("--config", default="configs/default.yaml"); ap.add_argument("--asof", default=None)
ap.add_argument("--prices", choices=["auto", "daily", "monthly"], default="auto")
args = ap.parse_args(); cfg = yaml.safe_load(open(args.config)); rc = cfg["refiners"]
out = Path(cfg["output"]["dir"]); out.mkdir(parents=True, exist_ok=True)
use_daily = args.prices == "daily" or (args.prices == "auto" and Path("data/prices_daily.csv").exists())
if use_daily:
    daily = pd.read_csv("data/prices_daily.csv", parse_dates=["date"]).set_index("date").drop(columns=["fetched"], errors="ignore")
else:
    daily = expand_monthly(pd.read_csv(rc["monthly_prices_file"], parse_dates=["date"], comment="#").set_index("date"))
print("prices:", "daily EIA spot" if use_daily else f"monthly averages from {rc['monthly_prices_file']}", "through", daily.dropna().index.max().date())
crack = benchmark_crack(daily, rc["benchmark"])
margins = load_margins(rc["margins_file"], rc["companies"])
bt = walk_forward(margins, crack, rc["min_train_quarters"])
sfx = "" if use_daily else "_monthly"          # the monthly run is committed as evidence; daily outputs stay local
if not bt.empty: bt.to_csv(out / f"refiner_backtest{sfx}.csv", index=False)
sc = score(bt, rc["bootstrap_draws"], rc["seed"])
asof = pd.Timestamp(args.asof) if args.asof else crack.index.max()
nc = nowcast(margins, crack, asof, rc["min_train_quarters"], bt)
if not nc.empty: nc.to_csv(out / "refiner_nowcast.csv", index=False); nc.to_csv(out / f"refiner_nowcast{sfx}.csv", index=False)
fits = {t: full_sample_fit(margins, crack, t) for t in rc["companies"]}
e = rc["eps_sensitivity"]; eps = e["throughput_kbd"] * 1000 * e["days"] * (1 - e["tax_rate"]) / (e["diluted_shares_mm"] * 1e6)
res = {"prices": "daily" if use_daily else "monthly", "score": sc, "in_sample_fit": fits, "nowcast": nc.to_dict(orient="records"), "eps_per_usd_bbl_per_quarter": eps}
(out / f"refiner_results{sfx}.json").write_text(json.dumps(res, indent=2, default=float))
print(json.dumps({k: v for k, v in res.items() if k != "nowcast"}, indent=2, default=float))
if not bt.empty: print(bt[["ticker", "quarter", "n_train", "crack", "pred", "naive", "actual"]].round(2).to_string(index=False))
print(nc.round(2).to_string(index=False) if not nc.empty else "no nowcast: not enough reported quarters")
