import json
from pathlib import Path

import pytest

from uzair import db

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return (FIX / name).read_text(encoding="utf-8")


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.init_db(c)
    yield c
    c.close()


def make_fetch(weather=None, aq=None, calls=None):
    """Fake HTTP: returns canned bodies; weather vs AQ chosen by URL. No real network."""
    from uzair.collector import HttpResult

    def fetch(url, timeout):
        if calls is not None:
            calls.append(url)
        body = aq if "air-quality" in url else weather
        if isinstance(body, HttpResult):
            return body
        return HttpResult(200, body, 5, None)
    return fetch
