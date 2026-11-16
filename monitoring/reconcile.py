"""Reconcile logical requests, HTTP attempts, failures, retained responses and observations (read-only).

One row of `collection_runs` is one LOGICAL request (one city, one endpoint, one poll), recorded after its
retry chain. `retry_count` is the number of retries made inside that chain, so
    HTTP attempts = logical requests + sum(retry_count).
`raw_responses` keeps the body of the final response of a request when one was received (HTTP 200, or an error
status with a body); a timeout or DNS error produces no body. An observation needs a stored weather response AND
a stored air-quality response of the same poll.

Prints COUNTS only (no air-quality or weather values).
Usage:  python -m monitoring.reconcile --db snapshots\\assessed_snapshot.db
"""
import argparse
from pathlib import Path

from monitoring.coverage import open_ro

SCOPE = "r.is_pilot = 0 AND r.acquisition_mode = 'scheduled'"


def reconcile(conn):
    one = lambda sql, *a: conn.execute(sql, a).fetchone()[0]
    out = {}
    out["logical"] = one(f"SELECT COUNT(*) FROM collection_runs r WHERE {SCOPE}")
    out["logical_weather"] = one(f"SELECT COUNT(*) FROM collection_runs r WHERE {SCOPE} AND endpoint='weather'")
    out["logical_aq"] = one(f"SELECT COUNT(*) FROM collection_runs r WHERE {SCOPE} AND endpoint='air_quality'")
    out["success"] = one(f"SELECT COUNT(*) FROM collection_runs r WHERE {SCOPE} AND status='success'")
    out["failed"] = one(f"SELECT COUNT(*) FROM collection_runs r WHERE {SCOPE} AND status<>'success'")
    out["retries_total"] = one(f"SELECT COALESCE(SUM(retry_count),0) FROM collection_runs r WHERE {SCOPE}")
    out["attempts"] = out["logical"] + out["retries_total"]
    out["success_retried"] = one(f"SELECT COUNT(*) FROM collection_runs r WHERE {SCOPE} AND status='success' AND retry_count>0")
    out["success_retries"] = one(f"SELECT COALESCE(SUM(retry_count),0) FROM collection_runs r WHERE {SCOPE} AND status='success'")
    out["failed_retries"] = one(f"SELECT COALESCE(SUM(retry_count),0) FROM collection_runs r WHERE {SCOPE} AND status<>'success'")
    out["failed_with_body"] = one(
        f"SELECT COUNT(*) FROM collection_runs r JOIN raw_responses w USING (run_id) WHERE {SCOPE} AND r.status<>'success'")
    out["failed_no_body"] = out["failed"] - out["failed_with_body"]
    out["retained"] = one(f"SELECT COUNT(*) FROM raw_responses w JOIN collection_runs r USING (run_id) WHERE {SCOPE}")
    out["retained_success"] = one(
        f"SELECT COUNT(*) FROM raw_responses w JOIN collection_runs r USING (run_id) WHERE {SCOPE} AND r.status='success'")
    out["retained_weather_ok"] = one(
        f"SELECT COUNT(*) FROM raw_responses w JOIN collection_runs r USING (run_id) WHERE {SCOPE} AND r.status='success' AND r.endpoint='weather'")
    out["retained_aq_ok"] = out["retained_success"] - out["retained_weather_ok"]
    out["observations"] = one("SELECT COUNT(*) FROM observations WHERE is_pilot=0 AND acquisition_mode='scheduled'")
    out["aq_without_observation"] = one(
        f"SELECT COUNT(*) FROM collection_runs r WHERE {SCOPE} AND endpoint='air_quality' AND status='success' "
        "AND run_id NOT IN (SELECT aq_run_id FROM observations)")
    out["weather_without_observation"] = one(
        f"SELECT COUNT(*) FROM collection_runs r WHERE {SCOPE} AND endpoint='weather' AND status='success' "
        "AND run_id NOT IN (SELECT weather_run_id FROM observations)")
    return out


def checks(o):
    """Identities that must hold; returns a list of (description, ok)."""
    return [
        ("logical = successful + failed", o["logical"] == o["success"] + o["failed"]),
        ("retries = retries of successful + retries of failed", o["retries_total"] == o["success_retries"] + o["failed_retries"]),
        ("failed = failed with a stored body + failed without a body", o["failed"] == o["failed_with_body"] + o["failed_no_body"]),
        ("retained = successful + failed with a body", o["retained"] == o["retained_success"] + o["failed_with_body"]),
        ("retained = logical - failed without a body", o["retained"] == o["logical"] - o["failed_no_body"]),
        ("observations = weather successes - weather successes without a pair",
         o["observations"] == o["retained_weather_ok"] - o["weather_without_observation"]),
        ("observations = air-quality successes - air-quality successes without a pair",
         o["observations"] == o["retained_aq_ok"] - o["aq_without_observation"]),
    ]


def report(o):
    lines = [
        "RECONCILIATION OF REQUESTS, ATTEMPTS AND RETAINED RESPONSES (scheduled, non-pilot)",
        f"1. logical requests (rows of collection_runs)        {o['logical']:>6}   weather {o['logical_weather']}, air quality {o['logical_aq']}",
        f"2. retries inside the logical requests                {o['retries_total']:>6}   successful requests {o['success_retries']}, failed requests {o['failed_retries']}",
        f"3. HTTP attempts = 1 + 2                              {o['attempts']:>6}",
        f"4. logical requests that succeeded                    {o['success']:>6}   of which needed retries {o['success_retried']}",
        f"5. logical requests that failed after all retries     {o['failed']:>6}   with a stored error body {o['failed_with_body']}, without a body {o['failed_no_body']}",
        f"6. retained raw responses                             {o['retained']:>6}   successful {o['retained_success']} (weather {o['retained_weather_ok']}, air quality {o['retained_aq_ok']}) + failed with a body {o['failed_with_body']}",
        f"7. valid observations                                 {o['observations']:>6}   air-quality successes without a weather pair {o['aq_without_observation']}, weather successes without an air-quality pair {o['weather_without_observation']}",
        "",
        "Identities:",
    ]
    lines += [f"   [{'ok' if ok else 'FAIL'}] {d}" for d, ok in checks(o)]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default="snapshots/assessed_snapshot.db")
    args = ap.parse_args(argv)
    if not Path(args.db).exists():
        raise SystemExit(f"database not found: {args.db}")
    conn = open_ro(args.db)
    try:
        o = reconcile(conn)
    finally:
        conn.close()
    print(report(o))
    return 0 if all(ok for _, ok in checks(o)) else 1


if __name__ == "__main__":
    raise SystemExit(main())