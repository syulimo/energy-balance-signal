"""Write notes/<week ending>.md from the latest fetched data. Run after the Wednesday EIA release:
  python scripts/fetch_eia.py && python scripts/fetch_cftc.py && python scripts/run_refiners.py && python scripts/make_note.py
Then fill in 'My read' and 'What would change my mind' by hand and commit."""
import argparse, yaml, pandas as pd
from pathlib import Path
from energy_balance.align import eia_public_dates
from energy_balance.notes import build_note
from energy_balance.pipeline import eia_features
from energy_balance.regime import load_events, regime_series

ap = argparse.ArgumentParser(); ap.add_argument("--config", default="configs/default.yaml")
cfg = yaml.safe_load(open(ap.parse_args().config))
rd = lambda p: pd.read_csv(p, parse_dates=["date"]).set_index("date").drop(columns=["fetched"], errors="ignore")
eia, cot, daily = rd("data/eia_weekly.csv"), rd("data/cot_wti.csv"), rd("data/prices_daily.csv")
cot_ulsd = rd("data/cot_ulsd.csv") if Path("data/cot_ulsd.csv").exists() else None
cal = pd.read_csv("data/release_calendar.csv", parse_dates=["week_ending", "release_date"])
feat = eia_features(eia, cfg); wk = feat.dropna(subset=["crude_reported_change_kb"]).index[-1]
rel = pd.Timestamp(eia_public_dates(pd.DatetimeIndex([wk]), cal).iloc[0])
regime = regime_series(pd.DatetimeIndex([rel]), load_events(cfg["regime"]["events_file"])).iloc[0]
nc_path = Path(cfg["output"]["dir"]) / "refiner_nowcast.csv"
nc = pd.read_csv(nc_path) if nc_path.exists() and nc_path.stat().st_size > 5 else None      # absent or empty until refiner_margins.csv is filled
out = Path(cfg["notes"]["dir"]); out.mkdir(exist_ok=True); path = out / f"{wk.date()}.md"
if path.exists():
    raise SystemExit(f"{path} exists; a note is written once and then edited by hand, not regenerated")
path.write_text(build_note(feat, cot, daily, cfg, regime, rel, nc, cot_ulsd)); print("wrote", path)
