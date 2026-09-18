"""From the commodity to the company: does the quarter-average benchmark crack forecast
the refining margin per barrel that a refiner reports about four weeks after quarter end?

This is the step an equity team cares about. The benchmark crack is public every day;
the reported margin is a company KPI that moves the stock on earnings day. If the
mapping is stable, the quarter's margin is largely known before the release.

Protocol, fixed before anything runs:
  - benchmark: Gulf Coast 3-2-1 crack against Brent, USD/bbl, averaged over calendar days
    of the fiscal quarter (Valero reports calendar quarters)
  - model: per company OLS, margin = a + b * crack, fitted only on quarters whose
    release_date is on or before the forecast date (the last day of the target quarter)
  - benchmark model: naive, the last margin the company had reported by that date
  - score: absolute error, pooled and per company, paired bootstrap on the difference
The reported margins are hand entered from company filings; every row carries its source
url. The repository ships Valero. Refiners define margin per barrel differently, which is
why the model is fitted per company and never pools levels across companies.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

GAL_PER_BBL = 42.0
REQUIRED = {"ticker", "fiscal_quarter", "period_end", "release_date", "metric", "value_usd_bbl", "source_url"}


def crack_321(gasoline_usd_gal: pd.Series, distillate_usd_gal: pd.Series, crude_usd_bbl: pd.Series) -> pd.Series:
    """Three barrels of crude into two of gasoline and one of distillate, per barrel of crude."""
    return ((2.0 * gasoline_usd_gal + distillate_usd_gal) / 3.0 * GAL_PER_BBL - crude_usd_bbl).rename("crack_321_usd_bbl")


def benchmark_crack(daily: pd.DataFrame, spec: dict) -> pd.Series:
    """spec = {gasoline: col, distillate: col, crude: col}; rows with any leg missing are dropped."""
    d = daily[[spec["gasoline"], spec["distillate"], spec["crude"]]].dropna()
    return crack_321(d[spec["gasoline"]], d[spec["distillate"]], d[spec["crude"]])


def expand_monthly(monthly: pd.DataFrame) -> pd.DataFrame:
    """Monthly average prices -> a business-day frame that carries each month's average on every
    business day of that month. A quarter mean of this frame is the business-day weighted mean of
    the monthly averages, so everything downstream (quarter averages as of a date, walk-forward,
    nowcast) runs unchanged on monthly data. The crack is linear in prices, so the crack of the
    monthly averages equals the monthly average of the daily crack."""
    parts = []
    for d, row in monthly.sort_index().iterrows():
        days = pd.bdate_range(d, d + pd.offsets.MonthEnd(0))
        parts.append(pd.DataFrame([row.to_numpy()] * len(days), index=days, columns=monthly.columns))
    return pd.concat(parts)


def full_sample_fit(margins: pd.DataFrame, daily_crack: pd.Series, ticker: str) -> dict:
    """In-sample OLS over every reported quarter. Descriptive only: it says what the slope and fit
    look like, not how well the model forecasts. The walk-forward score is the forecast evidence."""
    q = quarter_average(daily_crack); m = margins[(margins["ticker"] == ticker) & margins["quarter"].isin(q.index[q["complete"]])]
    x, y = q.loc[m["quarter"], "crack"].to_numpy(), m["value_usd_bbl"].to_numpy(); a, b = _fit(x, y); r = y - (a + b * x)
    return {"n": int(len(m)), "intercept": a, "slope": b, "r2": float(1 - (r ** 2).sum() / ((y - y.mean()) ** 2).sum()), "resid_sd": float(r.std(ddof=2))}


def quarter_average(daily: pd.Series, asof: pd.Timestamp | None = None) -> pd.DataFrame:
    """Mean by calendar quarter using only days on or before asof. 'days' and 'complete'
    tell the reader whether the last quarter is a finished quarter or quarter to date."""
    s = daily.loc[:asof] if asof is not None else daily
    g = s.groupby(s.index.to_period("Q"))
    out = pd.DataFrame({"crack": g.mean(), "days": g.size(), "last_day": g.apply(lambda x: x.index.max())})
    out["complete"] = out["last_day"] >= (out.index.end_time.normalize() - pd.Timedelta(days=4))   # tolerate a weekend or holiday at quarter end
    return out


def load_margins(path: str, tickers: list[str] | None = None) -> pd.DataFrame:
    m = pd.read_csv(path, parse_dates=["period_end", "release_date"], comment="#")
    if not REQUIRED <= set(m.columns):
        raise KeyError(f"{path} needs columns {sorted(REQUIRED)}")
    m["quarter"] = pd.PeriodIndex(m["fiscal_quarter"], freq="Q")
    if (m["release_date"] <= m["period_end"]).any():
        raise ValueError("a release_date on or before its period_end is a data entry error")
    if m.duplicated(["ticker", "quarter"]).any():
        raise ValueError("duplicate ticker and quarter rows")
    if tickers:
        m = m[m["ticker"].isin(tickers)]
    return m.sort_values(["ticker", "quarter"]).reset_index(drop=True)


def _fit(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """OLS intercept and slope. A crack with no variation in the training quarters gives slope 0 and the mean margin."""
    xv = x - x.mean(); ss = float((xv ** 2).sum())
    b = float((xv * (y - y.mean())).sum() / ss) if ss > 1e-12 else 0.0
    return float(y.mean() - b * x.mean()), b


def forecast_one(margins: pd.DataFrame, qavg: pd.DataFrame, ticker: str, target: pd.Period, asof: pd.Timestamp, min_train: int) -> dict | None:
    """Forecast `ticker`'s margin for `target` using only what was public at `asof`."""
    known = margins[(margins["ticker"] == ticker) & (margins["release_date"] <= asof) & (margins["quarter"] < target)]
    known = known[known["quarter"].isin(qavg.index)]
    if len(known) < min_train or target not in qavg.index:
        return None
    a, b = _fit(qavg.loc[known["quarter"], "crack"].to_numpy(), known["value_usd_bbl"].to_numpy())
    resid = known["value_usd_bbl"].to_numpy() - (a + b * qavg.loc[known["quarter"], "crack"].to_numpy())
    return {"ticker": ticker, "quarter": str(target), "asof": asof.date().isoformat(), "n_train": int(len(known)),
            "crack": float(qavg.loc[target, "crack"]), "intercept": a, "slope": b,
            "pred": a + b * float(qavg.loc[target, "crack"]), "naive": float(known.iloc[-1]["value_usd_bbl"]),
            "train_crack_max": float(qavg.loc[known["quarter"], "crack"].max()),
            "extrapolating": bool(qavg.loc[target, "crack"] > qavg.loc[known["quarter"], "crack"].max() or qavg.loc[target, "crack"] < qavg.loc[known["quarter"], "crack"].min()),
            "resid_sd": float(resid.std(ddof=2)) if len(known) > 2 else float("nan")}


def walk_forward(margins: pd.DataFrame, daily_crack: pd.Series, min_train: int = 8) -> pd.DataFrame:
    """One forecast per company and reported quarter, made on the last day of that quarter."""
    rows = []
    for _, r in margins.iterrows():
        asof = r["quarter"].end_time.normalize()
        f = forecast_one(margins, quarter_average(daily_crack, asof), r["ticker"], r["quarter"], asof, min_train)
        if f:
            rows.append({**f, "actual": float(r["value_usd_bbl"]), "release_date": r["release_date"].date().isoformat()})
    return pd.DataFrame(rows)


def score(bt: pd.DataFrame, draws: int = 1000, seed: int = 42) -> dict:
    """Mean absolute error of model and naive, paired bootstrap on the difference (naive minus
    model, so positive means the crack model is better), and the hit rate on the direction of
    the quarter-on-quarter change."""
    if bt.empty:
        return {"n": 0, "note": "not enough reported quarters to score"}
    def one(d):
        e_m, e_n = (d["actual"] - d["pred"]).abs().to_numpy(), (d["actual"] - d["naive"]).abs().to_numpy()
        rng = np.random.default_rng(seed); diff = e_n - e_m
        boots = np.array([rng.choice(diff, len(diff)).mean() for _ in range(draws)])
        moved = d[d["actual"] != d["naive"]]
        hit = float((np.sign(moved["pred"] - moved["naive"]) == np.sign(moved["actual"] - moved["naive"])).mean()) if len(moved) else float("nan")
        return {"n": int(len(d)), "mae_model": float(e_m.mean()), "mae_naive": float(e_n.mean()), "mae_gain_vs_naive": float(diff.mean()),
                "ci_low": float(np.percentile(boots, 2.5)), "ci_high": float(np.percentile(boots, 97.5)), "direction_hit_rate": hit}
    out = {"pooled": one(bt)}
    for t, d in bt.groupby("ticker"):
        out[t] = one(d)
    return out


def nowcast(margins: pd.DataFrame, daily_crack: pd.Series, asof: pd.Timestamp, min_train: int = 8, backtest: pd.DataFrame | None = None) -> pd.DataFrame:
    """Margin forecast for the quarter in progress at `asof`, from the quarter-to-date crack.
    The band is plus or minus 1.64 times the out-of-sample RMSE when a backtest exists for the
    company, otherwise the in-sample residual standard deviation. With so few quarters the
    band is indicative, not a calibrated interval."""
    qavg = quarter_average(daily_crack, asof); target = pd.Timestamp(asof).to_period("Q"); rows = []
    for t in sorted(margins["ticker"].unique()):
        f = forecast_one(margins, qavg, t, target, pd.Timestamp(asof), min_train)
        if not f:
            continue
        sd = f["resid_sd"]
        if backtest is not None and not backtest.empty and (backtest["ticker"] == t).sum() >= 4:
            d = backtest[backtest["ticker"] == t]; sd = float(np.sqrt(((d["actual"] - d["pred"]) ** 2).mean()))
        rows.append({**f, "days_in_quarter_so_far": int(qavg.loc[target, "days"]), "band_low": f["pred"] - 1.64 * sd, "band_high": f["pred"] + 1.64 * sd,
                     "change_vs_last_reported": f["pred"] - f["naive"]})
    return pd.DataFrame(rows)
