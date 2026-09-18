import numpy as np, pandas as pd, pytest, yaml
from energy_balance.regime import load_events, regime_series
from energy_balance.distillate import implied_distillate_change, diesel_crack, days_of_supply
from energy_balance.forecast import make_features, walk_forward, compare_to_naive
from energy_balance.scenario import ramp, run_scenarios
from energy_balance.align import eia_public_dates


def test_regime_from_events_file():
    ev = load_events("data/events.csv")
    idx = pd.date_range("2026-01-02", "2026-09-25", freq="W-FRI")
    r = regime_series(idx, ev)
    assert r.loc["2026-01-02"] == "pre"
    assert r.loc["2026-03-06"] == "war"
    assert r.loc["2026-06-05"] == "partial"
    assert r.loc["2026-09-18"] == "war"          # East-West pipeline shutdown 9/11 flips it back


def test_distillate_identity_and_crack():
    df = pd.DataFrame({"distillate_production": [5000.0], "distillate_imports": [100.0], "distillate_exports": [1300.0], "distillate_product_supplied": [3800.0], "distillate_stocks": [114000.0]})
    assert implied_distillate_change(df).iloc[0] == pytest.approx(0.0)
    assert days_of_supply(df).iloc[0] == pytest.approx(30.0)
    assert diesel_crack(pd.Series([3.0]), pd.Series([90.0])).iloc[0] == pytest.approx(36.0)


def test_walk_forward_never_uses_future():
    rng = np.random.default_rng(0); n = 200
    idx = pd.date_range("2020-01-03", periods=n, freq="W-FRI")
    x = pd.Series(rng.normal(size=n), index=idx, name="f")
    y = (2.0 * x.shift(1) + rng.normal(0, 0.1, n)).rename("y")        # y depends on lagged x only
    X = make_features(pd.DataFrame({"f": x}), ["f"], [1, 2])
    preds = walk_forward(y, X, train_window=52, refit_every=4, models=["naive", "ridge"])
    assert preds.index[0] > idx[52]
    res = compare_to_naive(y, preds, draws=200)
    assert res["ridge"]["ci_low"] > 0                                   # ridge beats naive, interval excludes zero


def test_holiday_release_calendar_overrides():
    idx = pd.date_range("2026-09-04", periods=2, freq="W-FRI")
    cal = pd.DataFrame({"week_ending": [pd.Timestamp("2026-09-04")], "release_date": [pd.Timestamp("2026-09-10")]})
    pub = eia_public_dates(idx, cal)
    assert pub.iloc[0] == pd.Timestamp("2026-09-10") and pub.iloc[1] == pd.Timestamp("2026-09-16")


def test_scenarios_are_monotone_and_relative():
    cfg = yaml.safe_load(open("configs/default.yaml"))
    sc = run_scenarios(cfg)
    assert (sc["incremental_balance_m12_mbd"] > 0).all()
    full = sc[(sc["reopening_fraction"] == 1.0) & (sc["months_to_full"] == 3)]["cum_stock_change_vs_today_12m_mb"].iloc[0]
    quarter = sc[(sc["reopening_fraction"] == 0.25) & (sc["months_to_full"] == 3)]["cum_stock_change_vs_today_12m_mb"].iloc[0]
    assert full > quarter
    assert ramp(10.0, 1.0, 5)[4] == pytest.approx(10.0)
