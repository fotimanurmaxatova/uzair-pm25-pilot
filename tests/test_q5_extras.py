"""Tests for analysis/q5_extras.py (error analysis, paired block bootstrap, leave-one-city-out).  Synthetic only."""
import numpy as np
import pytest

from analysis import cutoffs as cut
from analysis import data, modelling as m, q5_extras as q5
from tests.cp3_synth import SELECTED, all_and_dev
from analysis import evaluate as ev

ALL, DEV = all_and_dev()
TEST, _ = ev.test_pairs(ALL, True)
TRAIN = data.eligible(DEV, "train_final", native_only=True)


def tiny(ys, cities=None, hours=None):
    cities = cities or ["Tashkent"] * len(ys)
    hours = hours or [8] * len(ys)
    return [{"city": c, "valid_local": f"2026-11-07 {h:02d}:00", "target_pm25_t6": y,
             "valid_dt": cut.TEST_START_UTC} for c, y, h in zip(cities, ys, hours)]


def test_event_table_counts_hits_misses_false_alarms():
    y = np.array([10.0, 20.0, 40.0, 60.0])
    p = np.array([10.0, 40.0, 20.0, 60.0])
    e = q5.event_table(y, p, 35)
    assert (e["observed_events"], e["forecast_events"]) == (2, 2)
    assert (e["hits"], e["missed_events"], e["false_alarms"], e["correct_negatives"]) == (1, 1, 1, 1)
    assert q5.event_table(y, p, 50)["missed_events"] == 0        # a different threshold changes the counts


def test_error_analysis_groups_and_definitions():
    rows = tiny([10, 20, 40, 60], ["Tashkent", "Tashkent", "Nukus", "Nukus"], [8, 9, 8, 9])
    preds = {"full": np.array([12.0, 18.0, 40.0, 50.0]), "noweather": np.array([10.0, 20.0, 40.0, 60.0]),
             "persistence": np.array([20.0, 20.0, 20.0, 20.0])}
    ea = q5.error_analysis(rows, preds)
    assert set(ea["by_city"]) == {"Tashkent", "Nukus"} and set(ea["by_local_hour"]) == {"8", "9"}
    assert set(ea["by_observed_level"]) == {"<15", "15-35", "35-50", ">=50"}
    full_t = ea["by_city"]["Tashkent"]["full"]
    assert full_t["n"] == 2 and full_t["mean_residual"] == pytest.approx(0.0)      # (10-12 + 20-18)/2, observed - predicted
    assert ea["by_city"]["Nukus"]["full"]["mean_residual"] == pytest.approx(5.0)
    assert ea["by_city"]["Nukus"]["noweather"]["rmse"] == 0.0
    assert set(ea["events"]) == {"35", "25", "50"}
    assert q5.level_label(35.0) == "35-50" and q5.level_label(14.99) == "<15" and q5.level_label(50.0) == ">=50"


def test_error_analysis_needs_rows():
    with pytest.raises(ValueError):
        q5.error_analysis([], {})


def test_blocks_are_six_hour_and_common_to_all_cities():
    b = q5.block_index(TEST)
    assert b.min() == 0 and b.max() == 6                          # 42 origin hours -> 7 blocks
    by_time = {}
    for r, k in zip(TEST, b):
        by_time.setdefault(r["valid_dt"], set()).add(int(k))
    assert all(len(v) == 1 for v in by_time.values())             # same origin time -> same block for every city

def test_block_index_rejects_origin_before_test_start():
    row = tiny([10])[0]
    row["valid_dt"] = cut.TEST_START_UTC - cut.H

    with pytest.raises(ValueError, match="before"):
        q5.block_index([row])

def _preds(rng):
    y = m.targets(TEST)
    return {"full": y + rng.normal(0, 1, len(y)), "noweather": y + rng.normal(0, 3, len(y)),
            "persistence": m.persistence(TEST)}


def test_block_bootstrap_is_reproducible_and_paired():
    p = _preds(np.random.default_rng(0))
    a = q5.paired_block_bootstrap(TEST, p, reps=499, seed=7)
    b = q5.paired_block_bootstrap(TEST, p, reps=499, seed=7)
    c = q5.paired_block_bootstrap(TEST, p, reps=499, seed=8)
    assert a == b and a != c
    assert a["blocks"] == 7 and a["replications"] == 499 and "indicative" in a["note"]
    d = a["comparisons"]["full_minus_noweather"]
    assert d["rmse_difference"] < 0 and d["ci95"][0] <= d["rmse_difference"] <= d["ci95"][1] or d["ci95"][1] < 0
    assert d["share_replications_first_lower"] > 0.9
    assert a["skill"]["full"]["skill"] == pytest.approx(1 - a["rmse"]["full"] / a["rmse"]["persistence"])
    same = q5.paired_block_bootstrap(TEST, {"full": p["persistence"], "noweather": p["noweather"],
                                            "persistence": p["persistence"]}, reps=99)
    assert same["comparisons"]["full_minus_persistence"]["ci95"] == [0.0, 0.0]

def test_block_bootstrap_rejects_empty_input():
    with pytest.raises(ValueError, match="two six-hour blocks"):
        q5.paired_block_bootstrap(
            [],
            {"full": [], "noweather": [], "persistence": []},
            reps=9,
        )

def test_block_bootstrap_needs_two_blocks():
    one = [r for r in TEST if q5.block_index([r])[0] == 0][:5]
    with pytest.raises(ValueError, match="two six-hour blocks"):
        q5.paired_block_bootstrap(one, {"full": m.persistence(one), "noweather": m.persistence(one),
                                        "persistence": m.persistence(one)}, reps=9)

def test_block_bootstrap_rejects_prediction_length_mismatch():
    preds = {
        "full": np.array([1.0]),
        "noweather": m.persistence(TEST),
        "persistence": m.persistence(TEST),
    }
    with pytest.raises(ValueError, match="length"):
        q5.paired_block_bootstrap(TEST, preds)

def test_block_bootstrap_rejects_missing_model_prediction():
    preds = {
        "full": m.persistence(TEST),
        "noweather": m.persistence(TEST),
    }
    with pytest.raises(ValueError, match="exactly"):
        q5.paired_block_bootstrap(TEST, preds)

def test_block_bootstrap_rejects_extra_model_prediction():
    preds = {
        "full": m.persistence(TEST),
        "noweather": m.persistence(TEST),
        "persistence": m.persistence(TEST),
        "extra": m.persistence(TEST),
    }
    with pytest.raises(ValueError, match="exactly"):
        q5.paired_block_bootstrap(TEST, preds)

def test_block_bootstrap_rejects_non_finite_predictions():
    preds = {
        "full": np.array([np.nan] + [1.0] * (len(TEST) - 1)),
        "noweather": m.persistence(TEST),
        "persistence": m.persistence(TEST),
    }
    with pytest.raises(ValueError, match="finite"):
        q5.paired_block_bootstrap(TEST, preds)

def test_block_bootstrap_rejects_non_finite_targets():
    rows = tiny([np.inf])
    preds = {
        "full": np.array([1.0]),
        "noweather": np.array([1.0]),
        "persistence": np.array([1.0]),
    }
    with pytest.raises(ValueError, match="targets.*finite"):
        q5.paired_block_bootstrap(rows, preds)

def test_block_bootstrap_rejects_non_positive_replications():
    preds = {
        "full": m.persistence(TEST),
        "noweather": m.persistence(TEST),
        "persistence": m.persistence(TEST),
    }
    with pytest.raises(ValueError, match="reps"):
        q5.paired_block_bootstrap(TEST, preds, reps=0)

def test_loco_holds_out_each_city_and_codes_it_as_all_zeros():
    city = "Bukhara"
    pre, est = q5.fit_without_city(SELECTED["full"]["spec"], "full", TRAIN, city)
    assert pre.cities == [c for c in m.CITIES if c != city] and len(pre.cities) == 7
    held = [r for r in TEST if r["city"] == city]
    X = pre.transform(held, allow_unknown_city=True)
    assert X.shape[1] == 10 + 4 + 7 and X[:, -7:].sum() == 0      # all-zero indicators for the held-out city
    with pytest.raises(m.PreprocessError):
        pre.transform(held)                                       # not allowed outside LOCO
    ref = m.Preprocessor("full", scale=True, cities=pre.cities).fit([r for r in TRAIN if r["city"] != city])
    assert pre.state() == ref.state()                             # the held-out city never entered the training fit


def test_loco_result_shape_and_frozen_settings():
    res = q5.leave_one_city_out(TRAIN, TEST, SELECTED)
    assert [c["city"] for c in res["cities"]] == m.CITIES
    assert all(c["n_test"] == 14 and c["training_cities"] == 7 for c in res["cities"])
    assert res["pooled"]["n_test"] == 112 and "sensitivity" in res["note"]
    for c in res["cities"]:
        assert {"rmse_full", "rmse_noweather", "rmse_persistence", "skill_full", "skill_noweather"} <= set(c)

@pytest.mark.parametrize("bad_len", [0, 1, 5, 111, 113])
def test_block_bootstrap_rejects_any_wrong_prediction_length_including_broadcastable_one(bad_len):
    p = _preds(np.random.default_rng(0))
    n = len(TEST)                                   # 112
    full = p["full"]
    wrong = full[:bad_len] if bad_len < n else np.concatenate([full, full[: bad_len - n]])
    assert len(wrong) == bad_len
    with pytest.raises(ValueError, match="prediction length mismatch"):
        q5.paired_block_bootstrap(TEST, {**p, "full": wrong}, reps=9)