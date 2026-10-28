import sqlite3

import pytest

from uzair.db import connect, init_db


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "test.db")
    init_db(c)
    c.execute(
        "INSERT INTO collector_versions (version, registered_at_utc) "
        "VALUES ('test', '2026-10-28T00:00:00Z')"
    )
    for endpoint in ("weather", "air_quality"):
        c.execute(
            "INSERT INTO collection_runs (city_id, endpoint, started_at_utc, status, "
            "collector_version_id) VALUES (1, ?, '2026-10-28T06:05:00Z', 'success', 1)",
            (endpoint,),
        )
    c.commit()
    return c


def insert_obs(conn, **overrides):
    row = dict(
        city_id=1,
        observation_hour_utc="2026-10-28T06:00:00Z",
        weather_time_utc="2026-10-28T05:45:00Z",
        collected_at_utc="2026-10-28T06:05:10Z",
        weather_run_id=1,
        aq_run_id=2,
        relative_humidity_2m=29,
        wind_speed_ms=1.1,
        pm2_5=45.2,
        pm10=46.4,
        wind_speed_unit="m/s",
        aq_domain="cams_global",
        aq_interval_s=3600,
        weather_interval_s=900,
        is_native_step=1,
    )
    row.update(overrides)
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO observations ({cols}) VALUES ({marks})", list(row.values()))


def test_init_is_idempotent_and_seeds_eight_cities(conn):
    init_db(conn)  # a second run must change nothing
    assert conn.execute("SELECT COUNT(*) FROM cities").fetchone()[0] == 8


def test_valid_observation_is_stored(conn):
    insert_obs(conn)
    assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1


def test_duplicate_city_hour_is_blocked(conn):
    insert_obs(conn)
    with pytest.raises(sqlite3.IntegrityError):
        insert_obs(conn)


def test_wrong_wind_unit_is_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError):
        insert_obs(conn, wind_speed_unit="km/h")


def test_pm25_above_pm10_rejected_but_equal_allowed(conn):
    with pytest.raises(sqlite3.IntegrityError):
        insert_obs(conn, pm2_5=50.0, pm10=46.4)
    insert_obs(conn, pm2_5=46.4, pm10=46.4)  # boundary: equality is allowed


@pytest.mark.parametrize("humidity, ok", [(0, True), (100, True), (101, False), (-1, False)])
def test_humidity_boundaries(conn, humidity, ok):
    if ok:
        insert_obs(conn, relative_humidity_2m=humidity)
    else:
        with pytest.raises(sqlite3.IntegrityError):
            insert_obs(conn, relative_humidity_2m=humidity)