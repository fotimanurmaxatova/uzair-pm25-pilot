import json

from uzair import collector
from uzair.collector import HttpResult
from .conftest import load, make_fetch

W, A = load("weather_ok.json"), load("aq_ok.json")
no_sleep = lambda s: None


def test_null_pm25_goes_to_quarantine_not_observations(conn):
    d = json.loads(A)
    d["current"]["pm2_5"] = None
    res = collector.collect_all(conn, fetch=make_fetch(W, json.dumps(d)), sleep=no_sleep)
    assert set(res.values()) == {"quarantined"}
    assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0
    assert conn.execute("SELECT DISTINCT reason_code FROM quarantine").fetchone()[0] == "missing_value"
    # the air-quality run is the one quarantined; the weather run stays successful
    rows = {r["endpoint"]: r["status"] for r in conn.execute(
        "SELECT DISTINCT endpoint, status FROM collection_runs")}
    assert rows == {"weather": "success", "air_quality": "quarantined"}


def test_null_wind_speed_goes_to_quarantine_not_observations(conn):
    d = json.loads(W)
    d["current"]["wind_speed_10m"] = None
    res = collector.collect_all(conn, fetch=make_fetch(json.dumps(d), A), sleep=no_sleep)
    assert set(res.values()) == {"quarantined"}
    assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0
    assert conn.execute("SELECT DISTINCT reason_code FROM quarantine").fetchone()[0] == "missing_value"
    rows = {r["endpoint"]: r["status"] for r in conn.execute(
        "SELECT DISTINCT endpoint, status FROM collection_runs")}
    assert rows == {"weather": "quarantined", "air_quality": "success"}


def test_http_500_is_retried_then_recorded_as_failed(conn):
    server_error = HttpResult(500, "server error", 5, "HTTP 500")
    slept = []
    res = collector.collect_all(conn, fetch=make_fetch(server_error, server_error), sleep=slept.append)
    assert set(res.values()) == {"failed"}
    assert slept[:3] == [2, 4, 8]
    runs = conn.execute("SELECT http_status, retry_count, status FROM collection_runs").fetchall()
    assert all(r["http_status"] == 500 and r["retry_count"] == 3 and r["status"] == "failed" for r in runs)
    assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0