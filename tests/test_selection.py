"""Tests for analysis/modelling.py and analysis/selection.py (issue #15).  Synthetic rows only."""
import json
import random
from datetime import timedelta

import numpy as np
import pytest

from analysis import cutoffs as cut
from analysis import data, modelling as m, selection as sel
from analysis.data import GuardError
from monitoring import prepare

CITY_LIST = m.CITIES


def synthetic_raw(seed=1, hours=118, drop=None):
    """Eight cities, hourly rows from 2 Nov 00:00 local; every feature present; receipt = valid time + 5 min."""
    rnd = random.Random(seed)
    raw = []
    for ci, city in enumerate(CITY_LIST):
        for h in range(hours):
            t = cut.FIRST_ORIGIN_UTC + h * cut.H
            if drop and drop(city, h):
                continue
            base = 30 + 5 * ci + 8 * np.sin(h / 6.0) + rnd.gauss(0, 2)
            raw.append({"city": city, "observation_hour_utc": data.iso(t), "weather_time_utc": data.iso(t),
                        "collected_at_utc": data.iso(t + timedelta(minutes=5)),
                        "temperature_2m": 10 + rnd.gauss(0, 3), "relative_humidity_2m": 60 + rnd.gauss(0, 10),
                        "precipitation_mm": max(0.0, rnd.gauss(0, 0.3)), "wind_speed_ms": abs(rnd.gauss(3, 1)),
                        "wind_direction_deg": rnd.uniform(0, 360), "surface_pressure_hpa": 900 + rnd.gauss(0, 3),
                        "pm2_5": float(base), "pm10": float(base + 5), "nitrogen_dioxide": 20 + rnd.gauss(0, 4),
                        "ozone": 40 + rnd.gauss(0, 5)})
    return raw


@pytest.fixture(scope="module")
def rows():
    return data.build(synthetic_raw())


# ---------------- feature sets and fixed settings ----------------
def test_feature_sets_follow_the_protocol():
    full = m.FEATURE_SETS["full"]
    assert set(full["continuous"]) == {"pm2_5", "pm25_lag3", "pm25_lag6", "nitrogen_dioxide", "temperature_2m",
                                        "relative_humidity_2m", "precipitation_mm", "wind_speed_ms",
                                        "surface_pressure_hpa", "pressure_change_3h"}
    assert set(full["cyclic"]) == {"hour_sin", "hour_cos", "wind_dir_sin", "wind_dir_cos"}
    nw = m.FEATURE_SETS["noweather"]
    weather = {"temperature_2m", "relative_humidity_2m", "precipitation_mm", "wind_speed_ms",
               "surface_pressure_hpa", "pressure_change_3h", "wind_dir_sin", "wind_dir_cos"}
    assert not weather & set(nw["continuous"] + nw["cyclic"])
    assert "class_hours" not in full["continuous"] + full["cyclic"] and "weekday_local" not in full["continuous"]


def test_grid_and_fixed_hgb_parameters():
    ids = [m.candidate_id(s) for s in m.candidates()]
    assert len(ids) == 8 == len(set(ids))
    est = m.make_estimator({"model": "hgb", "max_depth": 5, "learning_rate": 0.1})
    p = est.get_params()
    assert (p["max_iter"], p["min_samples_leaf"], p["l2_regularization"], p["early_stopping"], p["random_state"]) == \
           (100, 5, 0.0, False, 0)
    assert (p["max_depth"], p["learning_rate"]) == (5, 0.1)
    assert m.make_estimator({"model": "ridge", "alpha": 10}).get_params()["alpha"] == 10


# ---------------- preprocessing is fitted on training rows only ----------------
def test_preprocessor_statistics_come_from_training_rows_only(rows):
    tr = data.eligible(rows, "cv1_train")
    va = data.eligible(rows, "cv1_valid")
    p1 = m.Preprocessor("full", scale=True).fit(tr)
    X1 = p1.transform(va)
    tampered = [dict(r, temperature_2m=1e6, nitrogen_dioxide=None) for r in va]    # change validation rows only
    p2 = m.Preprocessor("full", scale=True).fit(tr)
    assert p1.state() == p2.state()                       # fitting never saw the validation rows
    X2 = p2.transform(tampered)
    i = m.FEATURE_SETS["full"]["continuous"].index("temperature_2m")
    assert X2[:, i].max() == pytest.approx((p1.hi["temperature_2m"] - p1.mean["temperature_2m"]) / p1.std["temperature_2m"])
    assert X1.shape == X2.shape == (len(va), 10 + 4 + 8)

def test_standardisation_uses_population_std_and_zero_scale_fallback(rows):
    tr = data.eligible(rows, "cv1_train")
    feature = "temperature_2m"

    # Verify population standard deviation (ddof=0) after winsorisation.
    values = np.array([r[feature] for r in tr], dtype=float)
    lo, hi = np.percentile(values, [1, 99])
    clipped = np.clip(values, lo, hi)
    expected_sd = float(clipped.std(ddof=0))

    pre = m.Preprocessor("full", scale=True).fit(tr)
    assert pre.std[feature] == pytest.approx(expected_sd)

    # A constant training feature must use a safe scale of 1.0.
    constant_rows = [dict(r, **{feature: 7.0}) for r in tr]
    constant_pre = m.Preprocessor("full", scale=True).fit(constant_rows)
    assert constant_pre.std[feature] == 1.0

def test_winsorising_clips_continuous_but_not_cyclic_or_city(rows):
    tr = data.eligible(rows, "cv2_train")
    pre = m.Preprocessor("full", scale=False).fit(tr)
    extreme = [dict(tr[0], temperature_2m=1e9, wind_dir_sin=5.0, city="Nukus")]
    X = pre.transform(extreme)
    cont = m.FEATURE_SETS["full"]["continuous"]
    cyc = m.FEATURE_SETS["full"]["cyclic"]
    assert X[0, cont.index("temperature_2m")] == pytest.approx(pre.hi["temperature_2m"])
    assert X[0, len(cont) + cyc.index("wind_dir_sin")] == 5.0                    # cyclic features are not clipped
    assert X[0, len(cont) + len(cyc):].tolist() == [1.0 if c == "Nukus" else 0.0 for c in CITY_LIST]


def test_missing_features_use_training_median_and_targets_are_never_imputed(rows):
    tr = data.eligible(rows, "cv1_train")
    pre = m.Preprocessor("full", scale=False).fit(tr)
    X = pre.transform([dict(tr[0], precipitation_mm=None)])
    assert X[0, m.FEATURE_SETS["full"]["continuous"].index("precipitation_mm")] == pytest.approx(
        min(max(pre.median["precipitation_mm"], pre.lo["precipitation_mm"]), pre.hi["precipitation_mm"]))
    with pytest.raises(m.PreprocessError):
        m.targets([dict(tr[0], target_pm25_t6=None)])


def test_all_missing_training_feature_stops(rows):
    tr = [dict(r, nitrogen_dioxide=None) for r in data.eligible(rows, "cv1_train")]
    with pytest.raises(m.PreprocessError):
        m.Preprocessor("full", scale=True).fit(tr)


def test_unknown_city_is_rejected(rows):
    tr = data.eligible(rows, "cv1_train")
    pre = m.Preprocessor("noweather", scale=True).fit(tr)
    with pytest.raises(m.PreprocessError):
        pre.transform([dict(tr[0], city="Atlantis")])


# ---------------- persistence and RMSE ----------------
def test_persistence_is_the_pm25_at_origin(rows):
    va = data.eligible(rows, "cv1_valid")
    assert np.array_equal(m.persistence(va), np.array([r["pm2_5"] for r in va]))
    assert m.rmse([1, 2, 3], [1, 2, 5]) == pytest.approx(np.sqrt(4 / 3))


# ---------------- tie-break and ranking (0009) ----------------
def fake(spec, folds):
    return {"spec": spec, "folds": folds}


def test_tie_break_prefers_ridge_then_larger_alpha():
    res = {m.candidate_id(s): fake(s, [10.0, 10.0, 10.0]) for s in m.candidates()}
    assert sel.rank(res)[0][0] == "ridge_alpha100"


def test_tie_break_among_hgb_prefers_smaller_depth_then_smaller_rate():
    res = {m.candidate_id(s): fake(s, [10.0, 10.0, 10.0]) for s in m.candidates() if s["model"] == "hgb"}
    assert sel.rank(res)[0][0] == "hgb_depth3_lr0.05"
    res["hgb_depth5_lr0.05"] = fake({"model": "hgb", "max_depth": 5, "learning_rate": 0.05}, [9.0, 9.0, 9.0])
    assert sel.rank(res)[0][0] == "hgb_depth5_lr0.05"       # a clearly better mean beats parsimony


def test_ties_use_four_decimal_rounding():
    a = fake({"model": "hgb", "max_depth": 3, "learning_rate": 0.05}, [10.00001, 10.00001, 10.00001])
    b = fake({"model": "ridge", "alpha": 1}, [10.00004, 10.00004, 10.00004])
    assert sel.rank({"a": a, "b": b})[0][0] == "b"           # equal at 4 decimals -> Ridge
    c = fake({"model": "ridge", "alpha": 1}, [10.0002, 10.0002, 10.0002])
    assert sel.rank({"a": a, "c": c})[0][0] == "a"           # differs at 4 decimals -> lower mean wins


def test_criterion_is_the_unweighted_mean_of_fold_rmse():
    r = sel.rank({"x": fake({"model": "ridge", "alpha": 1}, [1.0, 2.0, 6.0])})
    assert r[0][1] == pytest.approx(3.0)


# ---------------- selection run ----------------
def test_selection_runs_on_synthetic_data_and_is_deterministic(rows):
    r1, r2 = sel.run_selection(rows), sel.run_selection(rows)
    assert r1 == r2
    assert len(r1["table"]) == 16 and {t["feature_set"] for t in r1["table"]} == {"full", "noweather"}
    for fs in ("full", "noweather"):
        picked = [t for t in r1["table"] if t["feature_set"] == fs and t["selected"]]
        assert len(picked) == 1 and picked[0]["mean_rmse"] == min(
            t["mean_rmse"] for t in r1["table"] if t["feature_set"] == fs)
        assert r1["selected"][fs]["candidate"] == picked[0]["candidate"]
    assert set(r1["counts"]) == {1, 2, 3} and len(r1["persistence_fold_rmse"]) == 3


def test_empty_fold_stops_selection():
    raw = synthetic_raw(drop=lambda c, h: 96 <= h)           # nothing after 5 Nov 23:00 local: folds 2/3 lose validation
    with pytest.raises(sel.SelectionError):
        sel.run_selection(data.build(raw))


def test_selection_rejects_test_origin_rows(rows):
    bad = dict(rows[0], valid_dt=cut.TEST_START_UTC)
    with pytest.raises(GuardError):
        sel.run_selection(rows + [bad])


def test_selection_uses_only_native_origins(rows):
    for k, (tr, va) in sel.fold_sets(rows).items():
        assert all(r["native"] for r in tr + va)


def test_outputs_are_written_once_and_never_overwritten(tmp_path, rows):
    res = sel.run_selection(rows)
    sel.write_outputs(res, tmp_path / "out")
    files = {p.name for p in (tmp_path / "out").iterdir()}
    assert files == {"cv_table.csv", "selected_configurations.json"}          # the manifest is written by analysis.integrity
    assert len((tmp_path / "out" / "cv_table.csv").read_text().strip().splitlines()) == 17
    with pytest.raises(sel.SelectionError, match="never written twice"):
        sel.write_outputs(res, tmp_path / "out")
