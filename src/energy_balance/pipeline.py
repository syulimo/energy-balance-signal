from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .align import align_release_dates
from .balance import adjustment, implied_stock_change, reported_stock_change, surprise
from .distillate import days_of_supply, diesel_crack, implied_distillate_change, reported_distillate_change
from .event_study import bootstrap_slope, bootstrap_spread, forward_returns, quantile_returns
from .forecast import compare_to_naive, make_features, walk_forward
from .positioning import managed_money_net, zscore
from .regime import load_events, regime_series
from .scenario import run_scenarios


def eia_features(eia: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Balances, surprises and flags on the EIA week-ending index. Used by the panel and by the weekly note."""
    m = cfg["model"]
    e = eia.copy()
    e = e.rename(columns={"production": "crude_production", "imports": "crude_imports", "exports": "crude_exports"})  # tolerate old names
    flows = e.rename(columns={"crude_production": "production", "crude_imports": "imports", "crude_exports": "exports"})
    e["crude_reported_change_kb"] = reported_stock_change(flows)
    e["crude_implied_change_kb"] = implied_stock_change(flows)
    e["crude_adjustment_kb"] = adjustment(flows)
    e["crude_consensus_proxy_kb"] = e["crude_reported_change_kb"].shift(1).rolling(m["consensus_window_weeks"], min_periods=m["consensus_window_weeks"]).mean()
    e["crude_surprise_kb"] = surprise(e["crude_reported_change_kb"], m["consensus_window_weeks"], m["consensus_proxy"])
    e["crude_surprise_z"] = zscore(e["crude_surprise_kb"], m["zscore_window_weeks"])
    adj_z = zscore(e["crude_adjustment_kb"], m["zscore_window_weeks"])
    e["adjustment_flag"] = adj_z.abs() > m["adjustment_flag_sd"]
    if "distillate_stocks" in e:
        e["distillate_reported_change_kb"] = reported_distillate_change(e)
        e["distillate_implied_change_kb"] = implied_distillate_change(e)
        e["distillate_surprise_kb"] = surprise(e["distillate_reported_change_kb"], m["consensus_window_weeks"])
        e["distillate_surprise_z"] = zscore(e["distillate_surprise_kb"], m["zscore_window_weeks"])
        e["distillate_days_of_supply"] = days_of_supply(e)
    return e


def build_panel(eia: pd.DataFrame, cot: pd.DataFrame, price: pd.DataFrame, cfg: dict, calendar: pd.DataFrame | None = None) -> pd.DataFrame:
    m = cfg["model"]
    e = eia_features(eia, cfg)
    c = cot.copy()
    c["mm_net"] = managed_money_net(c)
    c["mm_net_z"] = zscore(c["mm_net"], m["zscore_window_weeks"])
    panel = align_release_dates(e, c, price, calendar)
    if "ulsd" in panel and "close" in panel:
        panel["diesel_crack_usd_bbl"] = diesel_crack(panel["ulsd"], panel["close"])
    ev = load_events(cfg["regime"]["events_file"])
    panel["regime"] = regime_series(panel.index, ev)
    return panel


def run(eia: pd.DataFrame, cot: pd.DataFrame, price: pd.DataFrame, cfg: dict, calendar: pd.DataFrame | None = None) -> dict:
    es, fc = cfg["event_study"], cfg["forecast"]
    out = Path(cfg["output"]["dir"]); out.mkdir(parents=True, exist_ok=True)
    panel = build_panel(eia, cot, price, cfg, calendar)
    usable = panel.dropna(subset=["crude_surprise_z", "mm_net_z"])
    if len(usable) < es["min_weeks"]:
        raise ValueError(f"fewer than {es['min_weeks']} usable weeks")
    results = {"event_study": {}, "forecast": {}, "scenario": None, "n_weeks": int(len(usable)), "adjustment_flags": int(panel["adjustment_flag"].sum())}

    # event study, by regime if asked
    fwd = forward_returns(panel["close"], es["horizon_weeks"])
    signals = {"crude_surprise_z": -panel["crude_surprise_z"], "mm_net_z": -panel["mm_net_z"]}
    if "distillate_surprise_z" in panel: signals["distillate_surprise_z"] = -panel["distillate_surprise_z"]
    groups = {"all": panel.index}
    if es.get("by_regime"):
        for lab, idx in panel.groupby("regime").groups.items(): groups[str(lab)] = idx
        if (panel["regime"] != "pre").any():                       # war and partial together: every week since the first event
            groups["since_first_event"] = panel.index[panel["regime"] != "pre"]
    for gname, idx in groups.items():
        results["event_study"][gname] = {}
        for sname, sig in signals.items():
            sub = sig.loc[idx].dropna()
            if len(sub) < es.get("min_weeks_slope", 20):
                results["event_study"][gname][sname] = {"skipped": f"only {len(sub)} weeks"}; continue
            if len(sub) < es.get("min_weeks_quantile", 60):     # too short for quintiles: one slope with an interval
                results["event_study"][gname][sname] = {"method": "slope", **{h: bootstrap_slope(sub, fwd.loc[idx, h], es["bootstrap_draws"], es["seed"]) for h in fwd.columns}}; continue
            qt = quantile_returns(sub, fwd.loc[idx], es["quantiles"]); qt.to_csv(out / f"quantiles_{gname}_{sname}.csv")
            results["event_study"][gname][sname] = {h: bootstrap_spread(sub, fwd.loc[idx, h], es["quantiles"], es["bootstrap_draws"], es["seed"]) for h in fwd.columns}

    # forecast next week's crude print from lagged flows
    X = make_features(eia.rename(columns={"production": "crude_production", "imports": "crude_imports", "exports": "crude_exports"}), fc["features"], fc["lags"])
    y = e_target = reported_stock_change(eia.rename(columns={"crude_production": "production"})).shift(-1)  # next week's print
    y = y.reindex(X.index)
    preds = walk_forward(y, X, fc["train_window_weeks"], fc["refit_every_weeks"], fc["models"], fc["seed"])
    results["forecast"] = compare_to_naive(y, preds, fc["bootstrap_draws"], fc["seed"])
    preds.to_csv(out / "forecast_predictions.csv")

    # scenarios
    sc = run_scenarios(cfg); sc.to_csv(out / "hormuz_scenarios.csv", index=False)
    results["scenario"] = sc.to_dict(orient="records")

    panel.to_csv(out / "panel.csv")
    (out / "results.json").write_text(json.dumps(results, indent=2, default=float))
    return results
