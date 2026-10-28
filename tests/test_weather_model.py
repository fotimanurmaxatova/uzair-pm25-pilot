from uzair import collector
from .conftest import load, make_fetch

W, A = load("weather_ok.json"), load("aq_ok.json")
no_sleep = lambda s: None


def test_migration_0003_adds_weather_model_column(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(observations)")}
    assert "weather_model" in cols


def test_weather_request_names_the_model_explicitly(conn):
    calls = []
    collector.collect_all(conn, fetch=make_fetch(W, A, calls), sleep=no_sleep)
    weather_url = next(u for u in calls if "api.open-meteo.com/v1/forecast" in u)
    aq_url = next(u for u in calls if "air-quality" in u)
    assert "models=best_match" in weather_url
    assert "models=" not in aq_url  # air quality uses domains=, not models=


def test_each_observation_records_the_weather_model(conn):
    collector.collect_all(conn, fetch=make_fetch(W, A), sleep=no_sleep)
    models = {r[0] for r in conn.execute("SELECT weather_model FROM observations")}
    assert models == {"best_match"}
