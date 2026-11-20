"""Tests for analysis/cutoffs.py and analysis/data.py (issue #17).  Synthetic rows only (never analysed)."""
import sqlite3
from collections import Counter
from datetime import datetime, timedelta

import pytest

from analysis import cutoffs as cut
from analysis import data
from analysis.data import GuardError
from monitoring import coverage as cov
from monitoring import prepare
from tests.test_coverage import make_db

Z = lambda s: datetime.strptime(s, data.FMT).replace(tzinfo=cut.UTC)


def set_receipt(path, city, valid_utc, receipt_utc):
    c = sqlite3.connect(path)
    c.execute("UPDATE observations SET collected_at_utc=? WHERE observation_hour_utc=? AND city_id="
              "(SELECT city_id FROM cities WHERE name=?)", (receipt_utc, valid_utc, city))
    assert c.total_changes == 1
    c.commit()
    c.close()


def load(path):
    conn = cov.open_ro(path)
    try:
        return data.load_development(conn)
    finally:
        conn.close()


# ---------------- cut-off constants (one source of truth, 0009) ----------------
def test_cutoff_values_match_decision_0009():
    assert [data.iso(cut.FOLD_CUTOFF_UTC[k]) for k in (1, 2, 3)] == [
        "2026-11-03T19:00:00Z", "2026-11-04T19:00:00Z", "2026-11-05T19:00:00Z"]
    assert data.iso(cut.FINAL_CUTOFF_UTC) == "2026-11-06T17:00:00Z"
    assert data.iso(cut.TEST_START_UTC) == "2026-11-06T19:00:00Z"


def test_cutoffs_agree_with_monitoring_calendar():
    ref = cov.partitions()
    to_utc = lambda naive: naive.replace(tzinfo=cut.UTC) - cut.TZ
    for name, w in cut.partitions().items():
        a, b, c = ref[name]
        assert (w.first, w.last) == (to_utc(a), to_utc(b))
        if name.endswith("_train") or name == "train_final":
            assert w.cutoff == to_utc(c)


def test_test_partition_is_not_available():
    with pytest.raises(GuardError):
        data.eligible([], "test")
    assert "test" not in cut.partitions()


# ---------------- strict receipt-time boundary at the final cut-off ----------------
def test_row_exactly_at_final_cutoff_is_not_loaded_one_second_before_is(tmp_path):
    path = make_db(tmp_path)
    v = "2026-11-06T16:00:00Z"                              # origin hour before the cut-off
    set_receipt(path, "Tashkent", v, "2026-11-06T16:59:59Z")
    set_receipt(path, "Nukus", v, "2026-11-06T17:00:00Z")   # exactly at the cut-off
    set_receipt(path, "Samarkand", v, "2026-11-06T17:00:01Z")
    rows = {r["city"] for r in load(path) if r["valid_utc"] == v}
    assert "Tashkent" in rows and "Nukus" not in rows and "Samarkand" not in rows


def test_no_loaded_row_is_received_at_or_after_cutoff(tmp_path):
    rows = load(make_db(tmp_path))
    assert rows and all(Z(r["receipt_utc"]) < cut.FINAL_CUTOFF_UTC for r in rows)
    assert all(r["valid_dt"] < cut.TEST_START_UTC for r in rows)


# ---------------- guards raise instead of dropping ----------------
def test_test_origin_row_raises(tmp_path):
    path = make_db(tmp_path)
    v = "2026-11-06T19:00:00Z"                              # = 7 Nov 00:00 local, first test origin
    set_receipt(path, "Tashkent", v, "2026-11-06T10:00:00Z")   # tampered: "received" before the cut-off
    with pytest.raises(GuardError, match="test-origin"):
        load(path)


def test_build_rejects_row_received_at_cutoff_and_test_origin_directly():
    base = {"city": "X", "observation_hour_utc": "2026-11-06T12:00:00Z", "weather_time_utc": "2026-11-06T12:00:00Z",
            "collected_at_utc": "2026-11-06T12:05:00Z", **{f: 1.0 for f in prepare.FEATURES}}
    assert data.build([base])                                 # control: valid row passes
    for bad in ({**base, "collected_at_utc": "2026-11-06T17:00:00Z"},
                {**base, "observation_hour_utc": "2026-11-06T19:00:00Z"}):
        with pytest.raises(GuardError):
            data.build([bad])


# ---------------- fold-specific target receipt time ----------------
def test_cv1_train_target_received_at_fold_cutoff_is_excluded(tmp_path):
    origin = "2026-11-03T12:00:00Z"                           # last cv1 training origin (3 Nov 17:00 local), native
    target = "2026-11-03T18:00:00Z"
    assert cov.is_native(Z(origin))                # native origin
    def origins(path):
        return {(r["city"], r["valid_utc"]) for r in data.eligible(load(path), "cv1_train")}
    for sub, receipt, expect in (("before", "2026-11-03T18:59:59Z", True), ("at", "2026-11-03T19:00:00Z", False),
                                 ("after", "2026-11-03T19:00:01Z", False)):
        d = tmp_path / sub
        d.mkdir()
        path = make_db(d)
        set_receipt(path, "Tashkent", target, receipt)
        assert (("Tashkent", origin) in origins(path)) is expect


def test_validation_outcome_received_at_final_cutoff_is_not_used(tmp_path):
    # cv3 validation origin 6 Nov 15:00 local = 10:00Z; its target is valid 16:00Z
    path = make_db(tmp_path)
    set_receipt(path, "Tashkent", "2026-11-06T16:00:00Z", "2026-11-06T17:00:00Z")
    assert ("Tashkent", "2026-11-06T10:00:00Z") not in {(r["city"], r["valid_utc"])
                                                        for r in data.eligible(load(path), "cv3_valid")}


# ---------------- agreement with monitoring.prepare on a synthetic database ----------------
def prepare_counts(path):
    conn = cov.open_ro(path)
    try:
        rows = prepare.build(conn)
    finally:
        conn.close()
    hourly, native = Counter(), Counter()
    for r in rows:
        for p in filter(None, r["partitions"].split("|")):
            hourly[p] += 1
            native[p] += r["native"]
    return rows, hourly, native


def test_counts_match_monitoring_prepare_without_boundary_ties(tmp_path):
    path = make_db(tmp_path)
    _, hourly, native = prepare_counts(path)
    got = data.counts(load(path))
    for name in cut.partitions():
        assert got[name] == (hourly[name], native[name]), name


def test_derived_columns_match_prepare(tmp_path):
    path = make_db(tmp_path)
    ref, _, _ = prepare_counts(path)
    ref = {(r["city"], r["valid_utc"]): r for r in ref}
    same = ["native", "receipt_utc", "wind_dir_sin", "wind_dir_cos", "pressure_change_3h", "hour_sin", "hour_cos",
            "class_hours", "weekday_local", "high_pm25_35", "pm25_lag3", "pm25_lag6"] + prepare.FEATURES
    n = 0
    for r in load(path):
        p = ref[(r["city"], r["valid_utc"])]
        assert all(r[k] == p[k] for k in same), (r["city"], r["valid_utc"])
        if p["target_receipt_utc"] is None or Z(p["target_receipt_utc"]) < cut.FINAL_CUTOFF_UTC:
            assert (r["target_pm25_t6"], r["usable_pair"]) == (p["target_pm25_t6"], p["usable_pair"])
        n += 1
    assert n == 8 * 118                                   # slots received before 6 Nov 17:00Z


def test_database_is_not_modified(tmp_path):
    path = make_db(tmp_path)
    before = path.read_bytes()
    load(path)
    assert path.read_bytes() == before