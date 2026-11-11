"""Tests for monitoring/queries.py. Synthetic rows only (never analysed)."""
import hashlib
from pathlib import Path

import pytest

from monitoring import coverage as cov
from monitoring import queries as q
from tests.test_coverage import make_db


def open_(path):
    return cov.open_ro(path)


def test_full_week_has_24_rows_per_city_per_day(tmp_path):
    conn = open_(make_db(tmp_path))
    cities, table = q.daily_valid_by_city(conn)
    assert len(table) == 7 and len(cities) == 8
    assert all(n == 24 for day in table.values() for n in day.values())
    assert sum(n for day in table.values() for n in day.values()) == 1344


def test_local_day_uses_tashkent_time_not_utc(tmp_path):
    conn = open_(make_db(tmp_path))
    _, table = q.daily_valid_by_city(conn)
    assert min(table) == "2026-11-02" and max(table) == "2026-11-08"


def test_completeness_by_hour_counts_missing_poll(tmp_path):
    slot = cov.START + 5 * cov.H      # one poll missing for every city
    conn = open_(make_db(tmp_path, skip=lambda city, s: s == slot))
    got = {h: n for h, n, _ in q.completeness_by_hour(conn)}
    local_hour = (slot + cov.TZ).hour
    assert got[local_hour] == q.EXPECTED_PER_HOUR - 8
    assert got[(local_hour + 1) % 24] == q.EXPECTED_PER_HOUR


def test_failed_poll_shows_in_outcomes_and_failure_reasons(tmp_path):
    slot = cov.START + 20 * cov.H
    conn = open_(make_db(tmp_path, fail_slots=(slot,)))
    weather = [r for r in q.request_outcomes_by_day(conn) if r[1] == "weather"]
    assert sum(r[4] for r in weather) == 8                      # failed weather requests
    assert sum(r[2] for r in q.request_outcomes_by_day(conn)) == 168 * 8 * 2
    fails = q.failures_by_reason(conn)
    assert len(fails) == 1
    endpoint, http, reason, n, first, last = fails[0]
    assert (endpoint, http, reason, n) == ("weather", "503", "HTTP 503", 8)
    assert first == last


def test_retries_are_counted(tmp_path):
    path = make_db(tmp_path)
    import sqlite3
    c = sqlite3.connect(path)
    c.execute("UPDATE collection_runs SET retry_count = 2 WHERE run_id IN (1, 2, 3)")
    c.commit()
    c.close()
    rows = q.request_outcomes_by_day(open_(path))
    assert sum(r[5] for r in rows) == 3 and sum(r[6] for r in rows) == 6


def test_quarantine_by_reason_and_rate(tmp_path):
    path = make_db(tmp_path)
    import sqlite3
    c = sqlite3.connect(path)
    for run_id, reason in (
        (1, "out_of_range"),
        (2, "out_of_range"),
        (3, "missing_value"),
        (1, "missing_value"),
    ):
        c.execute(
            "INSERT INTO quarantine "
            "(run_id, reason_code, detail, quarantined_at_utc) "
            "VALUES (?,?,?,?)",
            (run_id, reason, "x", "2026-11-02T00:06:00Z")
        )
    c.commit()
    c.close()

    total, quarantined_requests, reasons = q.quarantine_by_reason(open_(path))

    assert total == 168 * 8 * 2
    assert quarantined_requests == 3
    assert reasons == [
    ("missing_value", 2),
    ("out_of_range", 2),
]


def test_no_quarantine_is_reported_explicitly(tmp_path, capsys):
    q.main(["--db", str(make_db(tmp_path)), "--query", "quarantine"])
    assert "none quarantined (0 of 2688 scheduled requests" in capsys.readouterr().out


def test_latency_summary_statistics(tmp_path):
    path = make_db(tmp_path)
    import sqlite3
    c = sqlite3.connect(path)
    c.execute("UPDATE collection_runs SET latency_ms = run_id WHERE endpoint = 'weather'")
    c.commit()
    c.close()
    rows = {r[0]: r for r in q.latency_summary(open_(path))}
    weather = rows["weather"]
    assert weather[1] == 1344 and weather[2] == min(
        r[0] for r in open_(path).execute("SELECT run_id FROM collection_runs WHERE endpoint='weather'"))
    assert rows["air_quality"][3] == 10 and rows["air_quality"][4] == 10     # constant latency in the fixture


def test_pilot_and_manual_rows_are_not_counted(tmp_path):
    conn = open_(make_db(tmp_path, pilot_extra=True))
    _, table = q.daily_valid_by_city(conn)
    assert sum(n for day in table.values() for n in day.values()) == 1344


def test_queries_never_read_outcome_values_and_never_write(tmp_path):
    source = Path(q.__file__).read_text()
    for forbidden in ("pm2_5", "pm10", "temperature", "wind_speed", "nitrogen", "ozone"):
        assert forbidden not in source
    path = make_db(tmp_path)
    before = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    assert q.main(["--db", str(path)]) == 0
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == before


def test_missing_database_is_a_clear_error(tmp_path):
    with pytest.raises(SystemExit):
        q.main(["--db", str(tmp_path / "nope.db")])
