"""Collector: request -> retry -> store raw -> validate -> store observation / quarantine.

Every API request is audited in collection_runs. The original response body is stored
unchanged in raw_responses with its SHA-256 (provenance). Valid time (api time) and
receipt time (collected_at_utc) are stored separately.
"""
import hashlib
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import NamedTuple, Optional

from . import validate

COLLECTOR_VERSION = "0.1.0"
TIMEOUT_S = 10
MAX_RETRIES = 3
BACKOFF_BASE_S = 2

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
AQ_DOMAIN = "cams_global"
WEATHER_MODEL = "best_match"  # requested explicitly and stored with every row (decision 0003)

WEATHER_PARAMS = {
    "current": "temperature_2m,relative_humidity_2m,precipitation,"
               "wind_speed_10m,wind_direction_10m,surface_pressure",
    "wind_speed_unit": "ms",   # Open-Meteo default is km/h
    "models": WEATHER_MODEL,
    "timeformat": "unixtime",
    "timezone": "GMT",
}
AQ_PARAMS = {
    "current": "pm10,pm2_5,nitrogen_dioxide,ozone",
    "domains": AQ_DOMAIN,
    "timeformat": "unixtime",
    "timezone": "GMT",
}


class HttpResult(NamedTuple):
    status: Optional[int]
    body: Optional[str]
    latency_ms: int
    error: Optional[str]


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_hex(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def http_get(url, timeout=TIMEOUT_S):
    """Real HTTP GET. Never raises: network problems come back as HttpResult.error."""
    start = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return HttpResult(resp.status, body, int((time.monotonic() - start) * 1000), None)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return HttpResult(exc.code, body, int((time.monotonic() - start) * 1000), f"HTTP {exc.code}")
    except Exception as exc:  # timeout, DNS, connection reset...
        return HttpResult(None, None, int((time.monotonic() - start) * 1000), f"{type(exc).__name__}: {exc}")


def _should_retry(res):
    return res.status is None or res.status == 429 or res.status >= 500


def fetch_with_retry(fetch, url, max_retries=MAX_RETRIES, sleep=time.sleep):
    """Retry transient failures (network, 429, 5xx) with exponential backoff.
    4xx (other than 429) is our bug, so it is not retried. Returns (result, retries)."""
    retries = 0
    res = fetch(url, TIMEOUT_S)
    while _should_retry(res) and retries < max_retries:
        sleep(BACKOFF_BASE_S * (2 ** retries))
        retries += 1
        res = fetch(url, TIMEOUT_S)
    return res, retries


def _git(*args):
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return ""

def current_version():
    commit = _git("rev-parse", "HEAD")
    dirty = bool(_git("status", "--porcelain", "--", "src", "migrations"))
    tag = (commit[:7] if commit else "nogit") + ("-dirty" if dirty else "")
    return f"{COLLECTOR_VERSION}+{tag}", commit or None

def register_version(conn, version=None):
    commit = None
    if version is None:
        version, commit = current_version()
    row = conn.execute("SELECT version_id FROM collector_versions WHERE version = ?", (version,)).fetchone()
    if row:
        return row["version_id"]
    cur = conn.execute(
        "INSERT INTO collector_versions (version, git_commit, registered_at_utc) VALUES (?, ?, ?)",
        (version, commit, now_iso()))
    conn.commit()
    return cur.lastrowid


def _build_url(base, params, city):
    q = dict(params, latitude=city["latitude"], longitude=city["longitude"])
    return f"{base}?{urllib.parse.urlencode(q, safe=',')}"


def _request(conn, ctx, city, endpoint):
    """One audited request. Returns (run_id, HttpResult, received_at_utc)."""
    base, params = (WEATHER_URL, WEATHER_PARAMS) if endpoint == "weather" else (AQ_URL, AQ_PARAMS)
    started = now_iso()
    res, retries = fetch_with_retry(ctx["fetch"], _build_url(base, params, city), sleep=ctx["sleep"])
    received = now_iso()
    ok = res.status == 200 and res.body is not None
    cur = conn.execute(
        "INSERT INTO collection_runs (city_id, endpoint, started_at_utc, http_status, latency_ms,"
        " retry_count, status, error_message, collector_version_id, acquisition_mode, is_pilot)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (city["city_id"], endpoint, started, res.status, res.latency_ms, retries,
         "success" if ok else "failed", None if ok else (res.error or "no body"),
         ctx["version_id"], ctx["mode"], ctx["is_pilot"]))
    run_id = cur.lastrowid
    if res.body is not None:  # keep the original response even for error pages
        conn.execute(
            "INSERT INTO raw_responses (run_id, received_at_utc, response_sha256, body) VALUES (?,?,?,?)",
            (run_id, received, sha256_hex(res.body), res.body))
    return run_id, res, received


def _quarantine(conn, run_id, err):
    conn.execute("UPDATE collection_runs SET status='quarantined', error_message=? WHERE run_id=?",
                 (err.reason_code, run_id))
    conn.execute(
        "INSERT INTO quarantine (run_id, reason_code, detail, quarantined_at_utc) VALUES (?,?,?,?)",
        (run_id, err.reason_code, err.detail, now_iso()))


def collect_city(conn, ctx, city):
    """Collect one city. Returns 'stored', 'failed', 'quarantined' or 'duplicate'."""
    w_run, w_res, w_recv = _request(conn, ctx, city, "weather")
    a_run, a_res, a_recv = _request(conn, ctx, city, "air_quality")
    conn.commit()
    if w_res.status != 200 or a_res.status != 200 or w_res.body is None or a_res.body is None:
        return "failed"

    weather = air = None
    try:
        weather = validate.validate_weather(w_res.body)
    except validate.ValidationError as err:
        _quarantine(conn, w_run, err)
    try:
        air = validate.validate_air_quality(a_res.body)
    except validate.ValidationError as err:
        _quarantine(conn, a_run, err)
    if weather is None or air is None:
        conn.commit()
        return "quarantined"

    try:
        validate.check_time_alignment(weather, air)
    except validate.ValidationError as err:
        _quarantine(conn, w_run, err)
        _quarantine(conn, a_run, err)
        conn.commit()
        return "quarantined"

    dup = conn.execute("SELECT 1 FROM observations WHERE city_id=? AND observation_hour_utc=?",
                       (city["city_id"], air["observation_hour_utc"])).fetchone()
    if dup:
        conn.execute("UPDATE collection_runs SET status='rejected', error_message='duplicate' WHERE run_id=?",
                     (a_run,))
        conn.commit()
        return "duplicate"

    row = {**weather, **air, "aq_domain": AQ_DOMAIN, "weather_model": WEATHER_MODEL, "city_id": city["city_id"],
           "collected_at_utc": max(w_recv, a_recv), "weather_run_id": w_run, "aq_run_id": a_run,
           "acquisition_mode": ctx["mode"], "is_pilot": ctx["is_pilot"]}
    cols = ", ".join(row)
    try:
        conn.execute(f"INSERT INTO observations ({cols}) VALUES ({', '.join('?' * len(row))})",
                     tuple(row.values()))
    except Exception as exc:  # a DB constraint caught something validate.py did not
        _quarantine(conn, a_run, validate.ValidationError("db_constraint", str(exc)))
        conn.commit()
        return "quarantined"
    conn.commit()
    return "stored"


def collect_all(conn, is_pilot=1, mode="scheduled", fetch=http_get, sleep=time.sleep):
    ctx = {"fetch": fetch, "sleep": sleep, "is_pilot": is_pilot, "mode": mode,
           "version_id": register_version(conn)}
    results = {}
    for city in conn.execute("SELECT city_id, name, latitude, longitude FROM cities ORDER BY city_id").fetchall():
        try:
            results[city["name"]] = collect_city(conn, ctx, city)
        except Exception as exc:  # one broken city must not stop the other seven
            conn.rollback()
            results[city["name"]] = f"error: {type(exc).__name__}"
    return results
