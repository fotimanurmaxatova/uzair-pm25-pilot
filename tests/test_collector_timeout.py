from uzair import collector
from uzair.collector import HttpResult
from .conftest import load

W, A = load("weather_ok.json"), load("aq_ok.json")


def test_requests_use_the_approved_10_second_timeout(conn):
    seen_timeouts = []

    def fetch(url, timeout):
        seen_timeouts.append(timeout)
        body = A if "air-quality-api.open-meteo.com" in url else W
        return HttpResult(200, body, 5, None)

    results = collector.collect_all(
        conn,
        fetch=fetch,
        sleep=lambda s: None,
    )

    assert set(results.values()) == {"stored"}
    assert len(seen_timeouts) == 16
    assert set(seen_timeouts) == {10}
