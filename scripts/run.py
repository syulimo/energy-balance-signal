"""Run on real data.  python scripts/run.py --config configs/default.yaml
Builds the Friday-close price frame from data/prices_daily.csv (WTI close, ULSD)."""
import argparse, json, yaml, pandas as pd
from energy_balance.pipeline import run
ap = argparse.ArgumentParser(); ap.add_argument("--config", default="configs/default.yaml")
cfg = yaml.safe_load(open(ap.parse_args().config))
eia = pd.read_csv("data/eia_weekly.csv", parse_dates=["date"]).set_index("date").drop(columns=["fetched"], errors="ignore")
cot = pd.read_csv("data/cot_wti.csv", parse_dates=["date"]).set_index("date")
daily = pd.read_csv("data/prices_daily.csv", parse_dates=["date"]).set_index("date").drop(columns=["fetched"], errors="ignore")
price = daily.resample("W-FRI").last().rename(columns={"wti_cushing": "close", "ulsd_nyh": "ulsd"})[["close", "ulsd"]]
cal = pd.read_csv("data/release_calendar.csv", parse_dates=["week_ending", "release_date"])
res = run(eia, cot, price, cfg, cal)
print(json.dumps({k: v for k, v in res.items() if k != "scenario"}, indent=2, default=float))
