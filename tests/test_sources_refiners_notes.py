import numpy as np, pandas as pd, pytest, yaml
from energy_balance.sources import cot_frame, eia_rows_to_series, eia_series_id, WTI_CODE
from energy_balance.refiners import benchmark_crack, crack_321, expand_monthly, forecast_one, load_margins, nowcast, quarter_average, score, walk_forward
from energy_balance.event_study import bootstrap_slope
from energy_balance.notes import build_note
from energy_balance.pipeline import eia_features


def test_eia_series_id_and_row_parsing():
    assert eia_series_id("WCESTUS1", "weekly") == "PET.WCESTUS1.W"
    assert eia_series_id("RWTC", "daily") == "PET.RWTC.D"
    assert eia_series_id("PET.RWTC.D", "daily") == "PET.RWTC.D"
    rows = [{"period": "2026-09-11", "value": "417500"}, {"period": "2026-09-04", "value": "418100"}, {"period": "2014-12-26", "value": "385000"}]
    s = eia_rows_to_series(rows, "crude_stocks_ex_spr", start="2015-01-02")
    assert list(s.index) == [pd.Timestamp("2026-09-04"), pd.Timestamp("2026-09-11")] and s.iloc[-1] == 417500.0
    with pytest.raises(ValueError):
        eia_rows_to_series([], "x")


@pytest.mark.parametrize("style", ["api", "text"])
def test_cot_frame_matches_on_contract_code_under_both_naming_styles(style):
    cols = {"api": ("cftc_contract_market_code", "report_date_as_yyyy_mm_dd", "m_money_positions_long_all", "m_money_positions_short_all", "open_interest_all", "market_and_exchange_names"),
            "text": ("CFTC_Contract_Market_Code", "Report_Date_as_YYYY-MM-DD", "M_Money_Positions_Long_All", "M_Money_Positions_Short_All", "Open_Interest_All", "Market_and_Exchange_Names")}[style]
    raw = pd.DataFrame([["067651", "2026-09-08T00:00:00.000", "250000", "90000", "2000000", "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE"],
                        ["067651", "2021-06-01T00:00:00.000", "400000", "40000", "2400000", "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE"],
                        ["022651", "2026-09-08T00:00:00.000", "30000", "20000", "300000", "NY HARBOR ULSD - NEW YORK MERCANTILE EXCHANGE"]], columns=cols)
    out = cot_frame(raw, WTI_CODE)
    assert len(out) == 2                                              # both names of the same contract, ULSD excluded
    assert out.index[-1] == pd.Timestamp("2026-09-04")                # Tuesday minus four days
    assert out.iloc[-1]["mm_long"] - out.iloc[-1]["mm_short"] == 160000


def test_crack_321_units():
    g, d, c = pd.Series([2.50]), pd.Series([3.10]), pd.Series([95.0])
    assert crack_321(g, d, c).iloc[0] == pytest.approx((2 * 2.50 + 3.10) / 3 * 42 - 95.0)


def _margins(tmp_path, days, crack, slope=0.6, noise=0.4, seed=0):
    rng = np.random.default_rng(seed); q = quarter_average(crack); rows = []
    for t, a in {"AAA": 2.0, "BBB": 5.0}.items():
        for per, r in q[q["complete"]].iterrows():
            rows.append({"ticker": t, "fiscal_quarter": str(per), "period_end": per.end_time.date(), "release_date": (per.end_time + pd.Timedelta(days=27)).date(),
                         "metric": "refining margin per barrel", "value_usd_bbl": round(a + slope * r["crack"] + rng.normal(0, noise), 2), "source_url": "synthetic"})
    p = tmp_path / "m.csv"; pd.DataFrame(rows).to_csv(p, index=False); return str(p)


@pytest.fixture
def crack():
    days = pd.date_range("2021-01-01", "2026-09-15", freq="D"); rng = np.random.default_rng(1)
    return pd.Series(18 + np.cumsum(rng.normal(0, 0.35, len(days))), index=days).clip(lower=4)


def test_quarter_average_respects_asof(crack):
    q = quarter_average(crack, pd.Timestamp("2026-08-15"))
    assert q.index[-1] == pd.Period("2026Q3") and not q.iloc[-1]["complete"] and q.iloc[-1]["days"] == 46
    assert q.loc[pd.Period("2026Q3"), "crack"] == pytest.approx(crack.loc["2026-07-01":"2026-08-15"].mean())


def test_forecast_ignores_margins_released_after_the_forecast_date(tmp_path, crack):
    m = load_margins(_margins(tmp_path, None, crack)); target = pd.Period("2025Q4"); asof = target.end_time.normalize()
    base = forecast_one(m, quarter_average(crack, asof), "AAA", target, asof, 8)
    m2 = m.copy(); late = (m2["ticker"] == "AAA") & (m2["release_date"] > asof)
    assert late.sum() >= 1
    m2.loc[late, "value_usd_bbl"] = 999.0                           # poison everything not yet public
    again = forecast_one(m2, quarter_average(crack, asof), "AAA", target, asof, 8)
    assert again["pred"] == pytest.approx(base["pred"]) and again["naive"] == pytest.approx(base["naive"])
    assert base["n_train"] == ((m["ticker"] == "AAA") & (m["release_date"] <= asof)).sum()


def test_planted_crack_relationship_beats_naive_and_null_does_not(tmp_path, crack):
    planted = score(walk_forward(load_margins(_margins(tmp_path, None, crack, slope=0.6)), crack, 8), draws=300)
    assert planted["pooled"]["mae_gain_vs_naive"] > 0 and planted["pooled"]["ci_low"] > 0
    null = score(walk_forward(load_margins(_margins(tmp_path, None, crack, slope=0.0, noise=1.0)), crack, 8), draws=300)
    assert null["pooled"]["ci_low"] < 0                               # no relationship: the interval must not exclude zero on the good side


def test_nowcast_is_for_the_quarter_in_progress(tmp_path, crack):
    m = load_margins(_margins(tmp_path, None, crack)); asof = pd.Timestamp("2026-09-15")
    nc = nowcast(m, crack, asof, 8, walk_forward(m, crack, 8))
    assert set(nc["quarter"]) == {"2026Q3"} and (nc["band_low"] < nc["pred"]).all() and (nc["pred"] < nc["band_high"]).all()
    assert (nc["days_in_quarter_so_far"] == 77).all()


def test_load_margins_rejects_release_before_period_end(tmp_path):
    p = tmp_path / "bad.csv"
    pd.DataFrame([{"ticker": "X", "fiscal_quarter": "2025Q1", "period_end": "2025-03-31", "release_date": "2025-03-30", "metric": "m", "value_usd_bbl": 1.0, "source_url": "u"}]).to_csv(p, index=False)
    with pytest.raises(ValueError):
        load_margins(str(p))


def test_bootstrap_slope_recovers_sign():
    rng = np.random.default_rng(5); x = pd.Series(rng.normal(size=30)); y = -0.02 * x + rng.normal(0, 0.005, 30)
    r = bootstrap_slope(x, y, 300)
    assert r["n"] == 30 and r["ci_high"] < 0


def test_weekly_note_has_numbers_blank_view_and_no_unpublished_positions():
    cfg = yaml.safe_load(open("configs/default.yaml")); rng = np.random.default_rng(2)
    weeks = pd.date_range("2024-01-05", "2026-09-11", freq="W-FRI"); n = len(weeks)
    eia = pd.DataFrame({"crude_stocks_ex_spr": 420000 + np.cumsum(rng.normal(0, 3000, n)), "crude_production": 13000.0, "crude_imports": 6000.0, "crude_exports": 4500.0,
                        "refinery_inputs": 16500 + rng.normal(0, 200, n), "refinery_utilization": 92.0, "crude_stocks_cushing": 24000.0,
                        "distillate_stocks": 105000 + np.cumsum(rng.normal(0, 900, n)), "distillate_production": 5000.0, "distillate_imports": 150.0,
                        "distillate_exports": 1400.0, "distillate_product_supplied": 3900.0}, index=weeks)
    cot = pd.DataFrame({"mm_long": 250000 + np.cumsum(rng.normal(0, 5000, n)), "mm_short": 90000.0, "open_interest": 2e6}, index=weeks)
    days = pd.date_range("2024-01-01", "2026-09-17", freq="B")
    daily = pd.DataFrame({"wti_cushing": 95.0, "brent": 103.0, "ulsd_nyh": 3.4}, index=days)
    text = build_note(eia_features(eia, cfg), cot, daily, cfg, "war", pd.Timestamp("2026-09-16"))
    assert "week ending 2026-09-11" in text and "## My read" in text and "written by hand" in text and "\u2014" not in text
    assert "positions as of 2026-09-08" in text                       # released Friday 2026-09-12; the 09-15 positions are not public on 09-16


def test_committed_margins_file_is_sourced_and_contiguous():
    m = load_margins("data/refiner_margins.csv")
    assert m["source_url"].str.startswith("http").all() and m["value_status"].isin(["primary", "secondary", "derived"]).all()
    assert m["value_usd_bbl"].between(0, 60).all()
    for t, d in m.groupby("ticker"):
        q = d["quarter"].sort_values().to_list()
        assert all((b - a).n == 1 for a, b in zip(q, q[1:])), f"{t} has a gap; the naive benchmark would silently use a stale quarter"
        assert (d["release_date"] - d["period_end"]).dt.days.between(14, 75).all()


def test_expand_monthly_gives_business_day_weighted_quarter_means():
    m = pd.DataFrame({"x": [10.0, 20.0, 40.0]}, index=pd.to_datetime(["2026-01-01", "2026-02-01", "2026-03-01"]))
    d = expand_monthly(m); w = [len(pd.bdate_range(s, s + pd.offsets.MonthEnd(0))) for s in m.index]
    assert len(d) == sum(w) and d.loc["2026-02-10", "x"] == 20.0
    assert quarter_average(d["x"]).loc[pd.Period("2026Q1"), "crack"] == pytest.approx(np.average([10, 20, 40], weights=w))


def test_committed_monthly_prices_are_complete_and_feed_the_benchmark():
    cfg = yaml.safe_load(open("configs/default.yaml"))["refiners"]
    m = pd.read_csv(cfg["monthly_prices_file"], parse_dates=["date"], comment="#").set_index("date")
    assert not m.isna().any().any() and (m.index.to_period("M")[1:] - m.index.to_period("M")[:-1] == pd.offsets.MonthEnd(1)).all()
    crack = benchmark_crack(expand_monthly(m), cfg["benchmark"])
    assert crack.loc["2024-10-15"] == pytest.approx((2 * 2.023 + 2.165) / 3 * 42 - 75.63)          # October 2024, by hand


def test_nowcast_flags_a_crack_outside_the_training_range(tmp_path, crack):
    m = load_margins(_margins(tmp_path, None, crack)); spiked = crack.copy(); spiked.loc["2026-07-01":] = crack.max() + 50
    assert nowcast(m, spiked, pd.Timestamp("2026-09-15"), 8)["extrapolating"].all()
    assert not nowcast(m, crack.clip(upper=crack.loc[:"2026-06-30"].max() - 1e-9).where(lambda s: s.index < "2026-07-01", crack.loc[:"2026-06-30"].median()), pd.Timestamp("2026-09-15"), 8)["extrapolating"].any()
