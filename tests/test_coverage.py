"""Tests for monitoring/coverage.py. Synthetic rows only (never analysed)."""
import sqlite3
from datetime import timedelta

import pytest

from monitoring import coverage as cov
from uzair import collector, db

D = timedelta(minutes=5)


def make_db(tmp_path, skip=lambda city, slot: False, fail_slots=(), late=lambda city, slot: timedelta(0), pilot_extra=False):
    path = tmp_path / "a.db"
    conn = db.connect(path)
    db.init_db(conn)
    vid = collector.register_version(conn, "test-v")
    cities = conn.execute("SELECT city_id, name FROM cities ORDER BY city_id").fetchall()
    iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")

    def run(city_id, endpoint, started, status="success", err=None, http=200, pilot=0):
        return conn.execute(
            "INSERT INTO collection_runs (city_id, endpoint, started_at_utc, http_status, latency_ms, retry_count,"
            " status, error_message, collector_version_id, acquisition_mode, is_pilot) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (city_id, endpoint, iso(started), http, 10, 0, status, err, vid, "scheduled", pilot)).lastrowid

    for k in range(cov.N_SLOTS):
        slot = cov.START + k * cov.H
        for c in cities:
            if slot in fail_slots:
                run(c["city_id"], "weather", slot + D, "failed", "HTTP 503", 503)
                run(c["city_id"], "air_quality", slot + D)
                continue
            if skip(c["name"], slot):
                continue
            recv = slot + D + late(c["name"], slot)
            w, a = run(c["city_id"], "weather", slot + D), run(c["city_id"], "air_quality", slot + D)
            conn.execute(
                "INSERT INTO observations (city_id, observation_hour_utc, weather_time_utc, collected_at_utc, weather_run_id,"
                " aq_run_id, wind_speed_ms, pm2_5, wind_speed_unit, aq_domain, aq_interval_s, weather_interval_s,"
                " is_native_step, acquisition_mode, is_pilot) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (c["city_id"], iso(slot), iso(slot), iso(recv), w, a, 2.0, 30.0, "m/s", "cams_global", 3600, 900,
                 1 if cov.is_native(slot) else 0, "scheduled", 0))
    if pilot_extra:   # a pilot row inside the window must never be counted
        conn.execute(
            "INSERT INTO observations (city_id, observation_hour_utc, weather_time_utc, collected_at_utc, weather_run_id,"
            " aq_run_id, wind_speed_ms, pm2_5, wind_speed_unit, aq_domain, aq_interval_s, weather_interval_s,"
            " is_native_step, acquisition_mode, is_pilot) SELECT city_id, '2026-11-09T00:00:00Z', '2026-11-09T00:00:00Z',"
            " '2026-11-09T00:05:00Z', weather_run_id, aq_run_id, 1, 1, 'm/s', 'x', 3600, 900, 0, 'manual', 1 FROM observations LIMIT 1")
    conn.commit()
    conn.close()
    return path


END = cov.START + 168 * cov.H + timedelta(hours=1)


def rep(path, now=END):
    conn = cov.open_ro(path)
    try:
        return cov.report(conn, now)
    finally:
        conn.close()


def test_approved_maxima_come_out_of_the_calendar_logic():
    full = cov.theoretical()
    assert sum(8 * v for k, v in full[False].items() if k == "test") == 336      # approved maximum test pairs
    assert 8 * full[True]["test"] == 112                                          # native 3-hourly equivalent
    assert 8 * full[True]["cv1_valid"] == 40


def test_complete_week_reports_full_coverage(tmp_path):
    out = rep(make_db(tmp_path, pilot_extra=True))
    assert "1344 of 1344 possible = 100.0%" in out
    assert "complete 168, partial 0, failed 0, missed 0" in out
    assert "longest gap 0 h" in out


def test_failed_poll_is_classified_with_reason_and_reduces_pairs(tmp_path):
    outage = cov.START + 15 * cov.H          # 15:00Z, a native step (as in the 2 Nov 503 incident)
    out = rep(make_db(tmp_path, fail_slots=(outage,)))
    assert "failed" in out and "weather failed HTTP 503 x8" in out
    assert "1336 of 1344" in out
    assert "longest gap 1 h" in out
    native_test = [l for l in out.splitlines() if l.strip().startswith("test ")][0]
    assert "112/112" in native_test or "/112" in native_test                      # outage is not inside the test window


def test_missed_poll_is_distinguished_from_failed(tmp_path):
    out = rep(make_db(tmp_path, skip=lambda c, s: s == cov.START + 30 * cov.H))
    assert "missed" in out and "no runs recorded" in out
    assert "complete 167, partial 0, failed 0, missed 1" in out


def test_partial_poll_one_city_missing(tmp_path):
    out = rep(make_db(tmp_path, skip=lambda c, s: c == "Nukus" and s == cov.START + 40 * cov.H))
    assert "partial" in out and "rows 7/8" in out


def test_gap_in_test_window_lowers_exact_pairs_not_next_row_substitution(tmp_path):
    slot = cov.START + (5 * 24 + 6) * cov.H        # Sat 7 Nov 06:00Z+... a valid time inside the test window
    path = make_db(tmp_path, skip=lambda c, s: c == "Tashkent" and s == slot)
    conn = cov.open_ro(path)
    cities, obs, _ = cov.load(conn)
    full = cov.theoretical()[False]["test"]
    assert cov.usable_pairs(obs["Tashkent"], False)["test"] < full               # lost origin(s) around the hole
    assert cov.usable_pairs(obs["Samarkand"], False)["test"] == full             # other cities unaffected
    conn.close()


def test_outcome_received_after_fitting_cutoff_is_not_usable(tmp_path):
    # rows valid 6 Nov 20:00-21:00 local arrive 2 h late (after the 22:00 fit cut-off), so the
    # origins 14:00 and 15:00 (outcomes 20:00 and 21:00) must drop out of the final training set
    late = lambda c, s: timedelta(hours=2) if cov.loc(s).day == 6 and cov.loc(s).hour in (20, 21) else timedelta(0)
    (tmp_path / "x").mkdir(), (tmp_path / "y").mkdir()
    on_time = rep(make_db(tmp_path / "x"))
    delayed = rep(make_db(tmp_path / "y", late=late))
    pick = lambda out: int([l for l in out.splitlines() if l.strip().startswith("train_final")][0].split()[1].split("/")[0])
    assert pick(on_time) - pick(delayed) == 2 * 8          # two origins x eight cities


def test_report_is_read_only(tmp_path):
    path = make_db(tmp_path)
    conn = cov.open_ro(path)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM observations")
    conn.close()


def test_elapsed_denominator_midweek(tmp_path):
    now = cov.START + timedelta(hours=24, minutes=10)       # 25 polls have started
    out = rep(make_db(tmp_path), now)
    assert "elapsed polls: 25/168" in out and "of 200 = " in out
