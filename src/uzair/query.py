"""Read-back and audit queries."""
import hashlib


def latest_observations(conn, limit=8):
    return conn.execute(
        "SELECT c.name, o.observation_hour_utc, o.collected_at_utc, o.pm2_5, o.wind_speed_ms,"
        " o.is_native_step, o.is_pilot FROM observations o JOIN cities c USING (city_id)"
        " ORDER BY o.obs_id DESC LIMIT ?", (limit,)).fetchall()


def provenance(conn, limit=8):
    """Latest observations with the audit trail of both API requests behind each row."""
    return conn.execute(
        "SELECT o.obs_id, c.name, o.observation_hour_utc, o.weather_time_utc, o.collected_at_utc,"
        " o.acquisition_mode, o.is_pilot, o.weather_model, o.aq_domain,"
        " wr.run_id AS w_run, wr.http_status AS w_http, wr.latency_ms AS w_ms, wr.retry_count AS w_retry,"
        " wraw.response_sha256 AS w_sha,"
        " ar.run_id AS a_run, ar.http_status AS a_http, ar.latency_ms AS a_ms, ar.retry_count AS a_retry,"
        " araw.response_sha256 AS a_sha, cv.version AS collector_version"
        " FROM observations o JOIN cities c USING (city_id)"
        " JOIN collection_runs wr ON wr.run_id = o.weather_run_id"
        " JOIN collection_runs ar ON ar.run_id = o.aq_run_id"
        " JOIN raw_responses wraw ON wraw.run_id = wr.run_id"
        " JOIN raw_responses araw ON araw.run_id = ar.run_id"
        " JOIN collector_versions cv ON cv.version_id = ar.collector_version_id"
        " ORDER BY o.obs_id DESC LIMIT ?", (limit,)).fetchall()


def verify_raw_hashes(conn):
    """Recompute SHA-256 of every stored raw response. Returns (checked, bad_run_ids)."""
    checked, bad = 0, []
    for r in conn.execute("SELECT run_id, body, response_sha256 FROM raw_responses"):
        checked += 1
        if hashlib.sha256(r["body"].encode("utf-8")).hexdigest() != r["response_sha256"]:
            bad.append(r["run_id"])
    return checked, bad


def counts(conn):
    """Small status summary: rows and run outcomes, split by pilot flag."""
    obs = conn.execute("SELECT is_pilot, COUNT(*) n FROM observations GROUP BY is_pilot").fetchall()
    runs = conn.execute("SELECT is_pilot, status, COUNT(*) n FROM collection_runs"
                        " GROUP BY is_pilot, status ORDER BY is_pilot, status").fetchall()
    return obs, runs
