"""Fetch weekly balance series and daily spot prices from the EIA API v2. Needs EIA_API_KEY.
Writes data/eia_weekly.csv and data/prices_daily.csv and records the fetch date.

  python scripts/fetch_eia.py                 # everything in the config
  python scripts/fetch_eia.py --check         # one series only, prints the head, for debugging
"""
import argparse, os, sys, yaml, requests, pandas as pd
from datetime import date
from energy_balance.sources import eia_rows_to_series, eia_series_id

ap = argparse.ArgumentParser(); ap.add_argument("--config", default="configs/default.yaml"); ap.add_argument("--check", action="store_true")
args = ap.parse_args(); cfg = yaml.safe_load(open(args.config))
key = os.environ.get(cfg["eia"]["api_key_env"])
if not key:
    sys.exit(f"set {cfg['eia']['api_key_env']} (free at https://www.eia.gov/opendata/)")


def pull(short_id: str, name: str, frequency: str) -> pd.Series:
    sid, rows, offset = eia_series_id(short_id, frequency), [], 0
    while True:                                   # the API caps a response at 5,000 rows
        r = requests.get(f"https://api.eia.gov/v2/seriesid/{sid}", timeout=60,
                         params={"api_key": key, "start": cfg["eia"]["start"], "offset": offset, "length": 5000})
        if r.status_code != 200:
            sys.exit(f"EIA {sid} ({name}): HTTP {r.status_code}\n{r.text[:400]}")
        body = r.json().get("response", {}); page = body.get("data", [])
        rows += page; offset += len(page)
        if len(page) < 5000 or offset >= int(body.get("total", 0) or 0):
            break
    return eia_rows_to_series(rows, name, cfg["eia"]["start"])


if args.check:
    name, sid = next(iter(cfg["eia"]["weekly"].items()))
    print(pull(sid, name, "weekly").tail()); sys.exit(0)

weekly = pd.concat([pull(sid, name, "weekly") for name, sid in cfg["eia"]["weekly"].items()], axis=1).sort_index()
weekly.index.name = "date"; weekly["fetched"] = str(date.today()); weekly.to_csv("data/eia_weekly.csv"); print(weekly.tail(3))
daily = pd.concat([pull(sid, name, "daily") for name, sid in cfg["eia"]["daily_prices"].items()], axis=1).sort_index()
daily.index.name = "date"; daily["fetched"] = str(date.today()); daily.to_csv("data/prices_daily.csv"); print(daily.tail(3))
