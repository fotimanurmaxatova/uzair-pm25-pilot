"""Tests for monitoring/prepare.py, audit.py and snapshot.py. Synthetic rows only."""
import csv
import hashlib
import json
import sqlite3
from datetime import timedelta

import pytest

from monitoring import audit, prepare, snapshot
from monitoring import coverage as cov
from tests.test_coverage import make_db

EPOCH0 = int(cov.START.timestamp())


def shaped(path):
    """pm2_5 = hours since START (so lags/targets are easy to read), pressure rises 1 hPa per hour."""
    c = sqlite3.connect(path)
    c.execute(f"UPDATE observations SET pm2_5 = (CAST(strftime('%s', observation_hour_utc) AS INTEGER) - {EPOCH0}) / 3600,"
              f" surface_pressure_hpa = 900 + (CAST(strftime('%s', observation_hour_utc) AS INTEGER) - {EPOCH0}) / 3600,"
              " wind_direction_deg = 90, temperature_2m = 10")
    c.commit()
    c.close()
    return path


def rows_of(path):
    conn = cov.open_ro(path)
    try:
        return prepare.build(conn)
    finally:
        conn.close()


def pick(rows, city, hours):
    t = (cov.START + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return next(r for r in rows if r["city"] == city and r["valid_utc"] == t)


# ---------------- prepare ----------------
def test_lags_target_and_derived_columns(tmp_path):
    rows = rows_of(shaped(make_db(tmp_path)))
    r = pick(rows, "Tashkent", 30)
    assert (r["pm25_lag3"], r["pm25_lag6"], r["target_pm25_t6"]) == (27, 24, 36)
    assert r["pressure_change_3h"] == 3 and r["usable_pair"] == 1
    assert round(r["wind_dir_sin"], 3) == 1.0 and round(r["wind_dir_cos"], 3) == 0.0
    assert r["valid_local"] == "2026-11-03 06:00"                  # START is 2 Nov 00:00 local, so +30 h
    assert len(rows) == 1344 and sum(r["native"] for r in rows) == 8 * 56


def test_missing_outcome_stays_missing_not_next_row(tmp_path):
    hole = cov.START + timedelta(hours=40)
    rows = rows_of(shaped(make_db(tmp_path, skip=lambda c, s: c == "Nukus" and s == hole)))
    r = pick(rows, "Nukus", 34)                                     # its t+6 h is the missing hour
    assert r["target_pm25_t6"] is None and r["usable_pair"] == 0
    assert pick(rows, "Tashkent", 34)["target_pm25_t6"] == 40


def test_class_hours_weekday_local_and_weekend(tmp_path):
    rows = rows_of(shaped(make_db(tmp_path)))
    mon_10 = pick(rows, "Tashkent", 10)                             # Mon 2 Nov 10:00 local
    mon_18 = pick(rows, "Tashkent", 18)                             # Mon 2 Nov 18:00 local (not class hours)
    sat_10 = pick(rows, "Tashkent", 5 * 24 + 10)                    # Sat 7 Nov 10:00 local
    assert (mon_10["class_hours"], mon_18["class_hours"], sat_10["class_hours"]) == (1, 0, 0)


def test_native_flag_uses_utc_grid_not_every_third_row(tmp_path):
    rows = rows_of(shaped(make_db(tmp_path)))
    r = pick(rows, "Tashkent", 2)                                   # 21:00Z = native
    assert r["native"] == 1 and pick(rows, "Tashkent", 3)["native"] == 0


def test_partition_tags_follow_the_calendar(tmp_path):
    rows = rows_of(shaped(make_db(tmp_path)))
    test_origin = pick(rows, "Tashkent", 5 * 24 + 2)               # Sat 7 Nov 02:00 local, native
    assert "test" in test_origin["partitions"].split("|")
    assert "train_final" not in test_origin["partitions"].split("|")
    train = pick(rows, "Tashkent", 2 * 24 + 8)                      # Wed 4 Nov 08:00 local
    assert "train_final" in train["partitions"].split("|")


def test_pilot_rows_never_enter_the_analysis_table(tmp_path):
    rows = rows_of(shaped(make_db(tmp_path, pilot_extra=True)))
    assert len(rows) == 1344


def test_csv_written_and_summary_has_counts_only(tmp_path):
    path = shaped(make_db(tmp_path))
    out = tmp_path / "d" / "rows.csv"
    prepare.main(["--db", str(path), "--out", str(out)])
    with open(out, encoding="utf-8") as fh:
        table = list(csv.DictReader(fh))
    assert list(table[0]) == prepare.COLUMNS and len(table) == 1344
    summ = prepare.summary(rows_of(path))
    assert "native (primary): 448" in summ and "test 336|112" in summ


# ---------------- audit ----------------
def add_raw(path, shift=lambda city: 0.05, same_cell=()):
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    for o in c.execute("SELECT o.weather_run_id w, o.aq_run_id a, c.name n, c.latitude la, c.longitude lo "
                       "FROM observations o JOIN cities c USING (city_id)").fetchall():
        la, lo = (41.0, 70.0) if o["n"] in same_cell else (o["la"] + shift(o["n"]), o["lo"])
        for rid in (o["w"], o["a"]):
            body = json.dumps({"latitude": la, "longitude": lo})
            c.execute("INSERT INTO raw_responses (run_id, received_at_utc, response_sha256, body) VALUES (?,?,?,?)",
                      (rid, "2026-11-02T00:05:05Z", hashlib.sha256(body.encode()).hexdigest(), body))
    c.commit()
    c.close()


def run_audit(path):
    conn = cov.open_ro(path)
    try:
        return audit.audit(conn)
    finally:
        conn.close()


def test_clean_database_reports_nothing_wrong(tmp_path):
    p = shaped(make_db(tmp_path))
    add_raw(p)
    out = run_audit(p)
    assert "weather 0, air quality 0" in out and "JUMPS" in out and ": 0\n" in out
    assert "location mismatch" not in out.lower()


def test_stale_receipt_is_counted(tmp_path):
    p = shaped(make_db(tmp_path, late=lambda c, s: timedelta(hours=3) if c == "Bukhara" and s == cov.START + 10 * cov.H else timedelta(0)))
    add_raw(p)
    assert "weather 1, air quality 1" in run_audit(p)


def test_large_jump_is_listed(tmp_path):
    p = shaped(make_db(tmp_path))
    c = sqlite3.connect(p)
    c.execute("UPDATE observations SET pm2_5 = 300 WHERE city_id = (SELECT city_id FROM cities WHERE name='Urgench') "
              "AND observation_hour_utc = '2026-11-03T10:00:00Z'")
    c.commit(), c.close()
    add_raw(p)
    out = run_audit(p)
    assert "Urgench" in out and "(|change in PM2.5| > 100 ug/m3 between consecutive hours): 2" in out   # up and back down


def test_location_echo_far_from_city_is_flagged(tmp_path):
    p = shaped(make_db(tmp_path))
    add_raw(p, shift=lambda n: 2.0 if n == "Nukus" else 0.05)
    out = run_audit(p)
    assert "Nukus" in out and "LOCATION ECHO" in out and "responses" in out
    assert "): 0 responses" not in out


def test_shared_grid_cell_and_identical_series_are_flagged(tmp_path):
    p = shaped(make_db(tmp_path))
    add_raw(p, same_cell=("Andijan", "Namangan"))
    out = run_audit(p)
    assert "shared cells" in out and "Andijan" in out and "Namangan" in out
    assert "!! " not in out.split("5. SERIES")[0]
    # shaped() makes every city identical, so the similarity check must flag pairs
    assert "!! " in out.split("5. SERIES")[1] and "100% identical" in out


# ---------------- snapshot ----------------
def test_snapshot_writes_files_manifest_and_matching_hashes(tmp_path):
    p = shaped(make_db(tmp_path))
    add_raw(p)
    log = tmp_path / "assessed.log"
    log.write_text("[Mon 11/02/2026  0:05:01.14] start\n", encoding="utf-8")
    out = tmp_path / "snap"
    m = snapshot.make_snapshot(p, out, log)
    assert m["row_counts"]["observations_valid_primary"] == 1344
    man = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
    for name, digest in man["files_sha256"].items():
        assert snapshot.sha256_file(out / name) == digest
    assert {"assessed_snapshot.db", "observations.csv", "collection_log.txt", "ATTRIBUTION.md"} <= set(man["files_sha256"])
    snap = sqlite3.connect(out / "assessed_snapshot.db")
    assert snap.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1344


def test_snapshot_refuses_a_database_with_a_tampered_raw_response(tmp_path):
    p = shaped(make_db(tmp_path))
    add_raw(p)
    c = sqlite3.connect(p)
    c.execute("UPDATE raw_responses SET body = '{}' WHERE raw_id = 1")
    c.commit(), c.close()
    with pytest.raises(SystemExit):
        snapshot.make_snapshot(p, tmp_path / "snap2")
    assert not (tmp_path / "snap2" / "MANIFEST.json").exists()


def test_missing_wind_direction_and_pressure_stay_missing(tmp_path):
    p = shaped(make_db(tmp_path))
    c = sqlite3.connect(p)
    c.execute("UPDATE observations SET wind_direction_deg = NULL, surface_pressure_hpa = NULL "
              "WHERE city_id = (SELECT city_id FROM cities WHERE name='Fergana') AND observation_hour_utc = '2026-11-02T12:00:00Z'")
    c.commit(), c.close()
    rows = rows_of(p)
    r = pick(rows, "Fergana", 17)                                    # 2026-11-02T12:00Z = START + 17 h
    assert r["wind_dir_sin"] is None and r["wind_dir_cos"] is None and r["pressure_change_3h"] is None
    assert pick(rows, "Fergana", 20)["pressure_change_3h"] is None   # its t-3 pressure is the missing one
    assert "wind_direction_deg 1" in prepare.summary(rows) and "pressure_change_3h 2" in prepare.summary(rows)


def test_outcome_received_after_fitting_cutoff_loses_the_training_tag(tmp_path):
    late = lambda c, s: timedelta(hours=2) if cov.loc(s).day == 6 and cov.loc(s).hour == 20 else timedelta(0)
    rows = rows_of(shaped(make_db(tmp_path, late=late)))
    origin = pick(rows, "Samarkand", 4 * 24 + 14)                  # Fri 6 Nov 14:00 local; outcome 20:00 arrives 22:05+2h
    assert origin["usable_pair"] == 1                              # the pair exists ...
    assert "train_final" not in origin["partitions"].split("|")    # ... but may not be used for the final fit
    assert "train_final" in pick(rows, "Samarkand", 4 * 24 + 13)["partitions"].split("|")
