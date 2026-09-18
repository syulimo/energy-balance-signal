"""Fetch the CFTC disaggregated futures-only report for NYMEX WTI and NY Harbor ULSD from
the CFTC Public Reporting Environment (no key). Writes data/cot_wti.csv and data/cot_ulsd.csv.
Contracts are matched on the CFTC contract market code, not the market name, because the
WTI contract was renamed in 2022."""
import argparse, sys, yaml, requests, pandas as pd
from energy_balance.sources import cot_frame

ap = argparse.ArgumentParser(); ap.add_argument("--config", default="configs/default.yaml")
cfg = yaml.safe_load(open(ap.parse_args().config))["cftc"]

for name, code in cfg["contracts"].items():
    r = requests.get(cfg["url"], timeout=120, params={"$where": f"cftc_contract_market_code='{code}' AND report_date_as_yyyy_mm_dd >= '{cfg['start']}'",
                                                       "$order": "report_date_as_yyyy_mm_dd", "$limit": 50000})
    if r.status_code != 200:
        sys.exit(f"CFTC {name}: HTTP {r.status_code}\n{r.text[:400]}")
    out = cot_frame(pd.DataFrame(r.json()), code)
    out.to_csv(f"data/cot_{name}.csv"); print(name, len(out), "weeks"); print(out.tail(3))
