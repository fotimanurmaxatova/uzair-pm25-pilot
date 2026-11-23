"""Tests for analysis/inference.py (Q1-Q4, wild cluster bootstrap, Holm, Rule A).  Synthetic rows only."""
import numpy as np
import pytest

from analysis import inference as inf
from tests.cp3_synth import all_and_dev

ALL, _ = all_and_dev()


def with_pm(fn, seed=0, noise=1.0):
    rng = np.random.default_rng(seed)
    return [dict(r, pm2_5=float(fn(r) + rng.normal(0, noise))) for r in ALL]


def test_webb_weights_have_mean_zero_and_unit_variance():
    assert inf.WEBB.mean() == pytest.approx(0.0) and (inf.WEBB ** 2).mean() == pytest.approx(1.0)
    assert len(inf.WEBB) == 6


def test_fit_cluster_ols_recovers_slope_and_rejects_degenerate_designs():
    rng = np.random.default_rng(1)
    n = 200
    x = rng.normal(size=n)
    cl = np.repeat(np.arange(5), 40)
    X = np.column_stack([x, np.ones(n)])
    beta, u, se = inf.fit_cluster_ols(X, 3 * x + 1 + rng.normal(0, 0.1, n), cl, 5)
    assert beta[0] == pytest.approx(3, abs=0.05) and se > 0
    with pytest.raises(inf.NotEstimable):
        inf.fit_cluster_ols(np.column_stack([x, x, np.ones(n)]), x, cl, 5)       # collinear
    with pytest.raises(inf.NotEstimable):
        inf.fit_cluster_ols(X, x, np.zeros(n, dtype=int), 1)                     # one cluster


def test_wild_cluster_test_detects_an_effect_and_not_a_null():
    rng = np.random.default_rng(2)
    n = 280
    cl = np.repeat(np.arange(7), 40)
    x = rng.normal(size=n)
    X = np.column_stack([x, np.ones(n)])
    strong = inf.wild_cluster_test(X, 2 * x + rng.normal(0, 1, n), cl, 7, reps=999, seed=3)
    null = inf.wild_cluster_test(X, rng.normal(0, 1, n), cl, 7, reps=999, seed=3)
    assert strong["p_wcr"] < 0.05 and strong["ci95_bootstrap_t"][0] > 0
    assert null["p_wcr"] > 0.05
    assert strong["clusters"] == 7 and strong["distinct_weight_combinations"] == 6 ** 7 and not strong["weights_repeat"]
    again = inf.wild_cluster_test(X, 2 * x + rng.normal(0, 1, n), cl, 7, reps=999, seed=3)
    assert again["replications"] == 999 and again["seed"] == 3


def test_five_clusters_repeat_weight_combinations():
    rng = np.random.default_rng(4)
    cl = np.repeat(np.arange(5), 30)
    X = np.column_stack([rng.normal(size=150), np.ones(150)])
    r = inf.wild_cluster_test(X, rng.normal(size=150), cl, 5, reps=9999, seed=1)
    assert r["distinct_weight_combinations"] == 7776 and r["weights_repeat"] is True


def test_sample_is_native_week_and_leave_one_day_removes_a_cluster():
    s = inf.sample(ALL)
    assert s and all(r["native"] and "2026-11-02" <= inf.local_date(r) <= "2026-11-08" for r in s)
    assert len(inf.sample(ALL, native=False)) > len(s)
    assert {inf.local_date(r) for r in inf.sample(ALL, drop_dates=("2026-11-04",))} == \
        {inf.local_date(r) for r in s} - {"2026-11-04"}
    assert {inf.local_date(r) for r in inf.sample(ALL, *inf.WEEKDAYS)} == {f"2026-11-0{d}" for d in range(2, 7)}


def test_q1_recovers_wind_effect_per_ms():
    rows = with_pm(lambda r: 30 - 2.5 * r["wind_speed_ms"], noise=0.5)
    e = inf.estimate(inf.sample(rows), "Q1", reps=499)
    assert e["estimate"] == pytest.approx(-2.5, abs=0.3) and e["clusters"] == 7 and e["p_wcr"] < 0.05


def test_q2_is_per_ten_percentage_points():
    rows = with_pm(lambda r: 0.5 * r["relative_humidity_2m"], noise=0.5)
    assert inf.estimate(inf.sample(rows), "Q2", reps=299)["estimate"] == pytest.approx(5.0, abs=0.6)


def test_q3_adjusts_for_controls():
    rows = with_pm(lambda r: 20 - 3 * r["wind_speed_ms"] + 0.8 * r["temperature_2m"] + 10 * r["precipitation_mm"], noise=0.5)
    e = inf.estimate(inf.sample(rows), "Q3", reps=299)
    assert e["estimate"] == pytest.approx(-3.0, abs=0.3)


def test_q4_uses_weekdays_only_five_clusters_and_percentage_points():
    rng = np.random.default_rng(5)
    rows = [dict(r, pm2_5=float(rng.choice([40.0, 20.0], p=[0.9, 0.1]) if r["class_hours"] else
                                rng.choice([40.0, 20.0], p=[0.1, 0.9]))) for r in ALL]
    for r in rows:
        r["high_pm25_35"] = int(r["pm2_5"] >= 35)
    e = inf.estimate(inf.sample(rows), "Q4", reps=299)
    assert e["clusters"] == 5 and e["estimate"] > 60 and e["distinct_weight_combinations"] == 7776   # percentage points
    assert e["n"] == len([r for r in inf.sample(rows) if "2026-11-02" <= inf.local_date(r) <= "2026-11-06"])


def test_incomplete_rows_are_dropped_and_counted():
    rows = [dict(r, wind_speed_ms=None) if i % 10 == 0 else r for i, r in enumerate(ALL)]
    e = inf.estimate(inf.sample(rows), "Q1", reps=99)
    assert e["dropped_incomplete"] > 0 and e["complete_cases"] + e["dropped_incomplete"] == e["rows_in_sample"]


def test_holm_adjustment():
    adj = inf.holm({"a": 0.01, "b": 0.04, "c": 0.03, "d": None})
    assert adj["a"] == pytest.approx(0.03) and adj["c"] == pytest.approx(0.06) and adj["b"] == pytest.approx(0.06)
    assert adj["d"] is None
    assert inf.holm({"a": 0.9, "b": 0.8})["a"] == 1.0


@pytest.mark.parametrize("primary,sens,expected", [
    (-3.0, [-1.0, -2.5, -0.1], "worth a longer study"),
    (-3.0, [-1.0, 0.5, -0.1], "inconclusive"),                  # unstable sign
    (-3.0, [-1.0, None], "inconclusive"),                       # a run that cannot be estimated
    (None, [-1.0], "inconclusive"),
    (-1.0, [-1.0, -0.5], "below practical threshold"),
    (-2.0, [-0.1], "worth a longer study"),                     # exactly at the threshold counts (<= -2)
    (0.0, [0.4, 1.0], "no support"),
    (0.5, [0.5, -0.2], "inconclusive"),
])
def test_rule_a(primary, sens, expected):
    assert inf.rule_a(primary, sens) == expected


def test_run_questions_structure_and_sensitivity_runs():
    rows = with_pm(lambda r: 30 - 2.5 * r["wind_speed_ms"], noise=0.5)
    res = inf.run_questions(rows, reps=99)
    assert set(res["primary_native"]) == {"Q1", "Q2", "Q3", "Q4"}
    assert all(res["primary_native"][q]["p_holm"] >= res["primary_native"][q]["p_wcr"] for q in res["primary_native"])
    assert len(res["sensitivity"]["leave_one_day_out"]) == 7
    assert set(res["sensitivity"]["weekday_only"]) == set(res["sensitivity"]["all_eligible_hourly_rows"]) == {"Q1", "Q2", "Q3"}
    assert len(res["rule_a"]["sensitivity_estimates"]) == 9
    assert res["rule_a"]["conclusion"] == "worth a longer study"
    assert res["sensitivity"]["weekday_only"]["Q3"]["clusters"] == 5


def test_inference_cli_needs_the_test_to_be_spent(tmp_path):
    from analysis import evaluate as ev
    with pytest.raises(ev.EvaluationGuardError, match="has not been run"):
        inf.main(["--db", "nope.db", "--repo", str(tmp_path)])
