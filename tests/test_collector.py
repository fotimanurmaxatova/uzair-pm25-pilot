import hashlib
import json

from uzair import collector, query
from uzair.collector import HttpResult
from .conftest import load, make_fetch


W, A = load("weather_ok.json"), load("aq_ok.json")
no_sleep = lambda s: None


def test_stored_and_readable_with_provenance(conn):
    res = collector.collect_all(conn, fetch=make_fetch(W, A), sleep=no_sleep)
    assert set(res.values()) == {"stored"}  # uniqueness is per (city, valid time): 8 cities, 8 rows
    assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 8
    row = query.latest_observations(conn, 1)[0]
    assert row["pm2_5"] == 31.5 and row["is_pilot"] == 1
    raw = conn.execute("SELECT body, response_sha256 FROM raw_responses LIMIT 1").fetchone()
    assert raw["response_sha256"] == hashlib.sha256(raw["body"].encode()).hexdigest()


def test_valid_time_and_receipt_time_are_separate(conn):
    collector.collect_all(conn, fetch=make_fetch(W, A), sleep=no_sleep)
    o = conn.execute("SELECT * FROM observations LIMIT 1").fetchone()
    assert o["observation_hour_utc"] == "2026-11-02T04:00:00Z"   # valid time from the API (fixture)
    assert o["weather_time_utc"] == "2026-11-02T04:05:00Z"
    assert o["collected_at_utc"] != o["observation_hour_utc"]


def test_request_asks_for_ms_and_unixtime(conn):
    calls = []
    collector.collect_all(conn, fetch=make_fetch(W, A, calls), sleep=no_sleep)
    weather_url = next(u for u in calls if "api.open-meteo.com/v1/forecast" in u)
    assert "wind_speed_unit=ms" in weather_url and "timeformat=unixtime" in weather_url


def test_timeout_retries_then_fails_and_is_audited(conn):
    timeout = HttpResult(None, None, 20000, "TimeoutError: timed out")
    calls, slept = [], []
    res = collector.collect_all(conn, fetch=make_fetch(timeout, timeout, calls), sleep=slept.append)
    assert set(res.values()) == {"failed"}
    assert slept[:3] == [2, 4, 8]                       # exponential backoff
    runs = conn.execute("SELECT status, retry_count FROM collection_runs").fetchall()
    assert all(r["status"] == "failed" and r["retry_count"] == 3 for r in runs)
    assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0


def test_4xx_is_not_retried(conn):
    bad = HttpResult(400, '{"error":true}', 5, "HTTP 400")
    slept = []
    collector.collect_all(conn, fetch=make_fetch(bad, bad), sleep=slept.append)
    assert slept == []


def test_bad_unit_goes_to_quarantine_not_observations(conn):
    d = json.loads(W)
    d["current_units"]["wind_speed_10m"] = "km/h"
    res = collector.collect_all(conn, fetch=make_fetch(json.dumps(d), A), sleep=no_sleep)
    assert set(res.values()) == {"quarantined"}
    assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0
    assert conn.execute("SELECT reason_code FROM quarantine").fetchone()[0] == "wrong_wind_unit"
    # original response still preserved
    assert conn.execute("SELECT COUNT(*) FROM raw_responses").fetchone()[0] == 16


def test_duplicate_is_detected_not_overwritten(conn):
    collector.collect_all(conn, fetch=make_fetch(W, A), sleep=no_sleep)
    before = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    res = collector.collect_all(conn, fetch=make_fetch(W, A), sleep=no_sleep)
    assert set(res.values()) == {"duplicate"}
    assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == before


def test_assessed_flag_stores_is_pilot_zero(conn):
    collector.collect_all(conn, is_pilot=0, fetch=make_fetch(W, A), sleep=no_sleep)
    assert conn.execute("SELECT DISTINCT is_pilot FROM observations").fetchone()[0] == 0
