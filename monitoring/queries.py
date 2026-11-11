"""Read-only stakeholder queries on the audit trail of the assessed collection.

Six named queries for the campus safety office / advisor ("is the collection reliable?"):
  1 daily_valid_by_city       valid rows per local day and city (expected 24 per city per day)
  2 completeness_by_hour      valid rows per local hour of day (all cities) against the maximum
  3 request_outcomes_by_day   requests, successes, failures, retried requests, retries per day and endpoint
  4 quarantine_by_reason      quarantined records by reason code, and the quarantine rate
  5 latency_summary           API latency (min, median, 95th percentile, max) per endpoint
  6 failures_by_reason        failed requests grouped by endpoint, HTTP status and error text, with first/last time

All queries read operational metadata only (timestamps, request status, counts, latency and errors).
They do not select PM2.5 or weather measurement values and must not be used for model selection.
They aggregate scheduled records across the database, including operational metadata from the test period.
The database is opened read-only. Local day = Asia/Tashkent (UTC+5, no DST); stored times are UTC.
Only scheduled, non-pilot rows are counted (the assessed data).

Usage:  python -m monitoring.queries [--db data/assessed.db] [--query NAME]
"""
import argparse
import math
from pathlib import Path

from monitoring.coverage import N_CITIES, N_SLOTS, open_ro

SCOPE = "is_pilot = 0 AND acquisition_mode = 'scheduled'"
LOCAL = "'+5 hours'"
CITY_DAYS = N_SLOTS // 24          # 7 local days
EXPECTED_PER_HOUR = CITY_DAYS * N_CITIES   # 56 rows per local hour of day


def daily_valid_by_city(conn):
    rows = conn.execute(
        f"SELECT date(o.observation_hour_utc, {LOCAL}) AS day, c.name AS city, COUNT(*) AS n "
        f"FROM observations o JOIN cities c USING (city_id) WHERE o.{SCOPE.replace(' AND ', ' AND o.')} "
        "GROUP BY day, c.city_id ORDER BY day, c.city_id").fetchall()
    cities = [r[0] for r in conn.execute("SELECT name FROM cities ORDER BY city_id")]
    days = sorted({r[0] for r in rows})
    table = {d: {c: 0 for c in cities} for d in days}
    for day, city, n in rows:
        table[day][city] = n
    return cities, table


def completeness_by_hour(conn):
    got = dict(conn.execute(
        f"SELECT CAST(strftime('%H', observation_hour_utc, {LOCAL}) AS INTEGER) AS hr, COUNT(*) "
        f"FROM observations WHERE {SCOPE} GROUP BY hr"))
    return [(h, got.get(h, 0), EXPECTED_PER_HOUR) for h in range(24)]


def request_outcomes_by_day(conn):
    return conn.execute(
        f"SELECT date(started_at_utc, {LOCAL}) AS day, endpoint, COUNT(*) AS requests, "
        "SUM(status = 'success') AS ok, SUM(status <> 'success') AS failed, "
        "SUM(retry_count > 0) AS retried, SUM(retry_count) AS retries "
        f"FROM collection_runs WHERE {SCOPE} GROUP BY day, endpoint ORDER BY day, endpoint").fetchall()


def quarantine_by_reason(conn):
    total = conn.execute(
        f"SELECT COUNT(*) FROM collection_runs WHERE {SCOPE}"
    ).fetchone()[0]

    quarantined_requests = conn.execute(
        "SELECT COUNT(DISTINCT r.run_id) "
        "FROM quarantine q JOIN collection_runs r USING (run_id) "
        f"WHERE r.{SCOPE.replace(' AND ', ' AND r.')}"
    ).fetchone()[0]

    reasons = conn.execute(
        "SELECT q.reason_code, COUNT(*) "
        "FROM quarantine q JOIN collection_runs r USING (run_id) "
        f"WHERE r.{SCOPE.replace(' AND ', ' AND r.')} "
        "GROUP BY q.reason_code "
        "ORDER BY COUNT(*) DESC, q.reason_code"
    ).fetchall()

    return total, quarantined_requests, reasons

def _percentile(sorted_values, p):
    k = max(0, math.ceil(p / 100 * len(sorted_values)) - 1)       # nearest rank
    return sorted_values[k]


def latency_summary(conn):
    out = []
    for endpoint in ("weather", "air_quality"):
        vals = sorted(r[0] for r in conn.execute(
            f"SELECT latency_ms FROM collection_runs WHERE {SCOPE} AND status = 'success' "
            "AND endpoint = ? AND latency_ms IS NOT NULL", (endpoint,)))
        if not vals:
            out.append((endpoint, 0, None, None, None, None))
            continue
        mid = len(vals) // 2
        median = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2
        out.append((endpoint, len(vals), vals[0], median, _percentile(vals, 95), vals[-1]))
    return out


def failures_by_reason(conn):
    return conn.execute(
        "SELECT endpoint, COALESCE(CAST(http_status AS TEXT), '-') AS http, "
        "COALESCE(substr(error_message, 1, 70), '-') AS reason, COUNT(*) AS n, "
        "MIN(started_at_utc) AS first_utc, MAX(started_at_utc) AS last_utc "
        f"FROM collection_runs WHERE {SCOPE} AND status <> 'success' "
        "GROUP BY endpoint, http, reason ORDER BY first_utc").fetchall()


def _print_daily(conn):
    cities, table = daily_valid_by_city(conn)
    print("1. DAILY VALID ROWS BY CITY (local day; expected 24 per city per day)")
    print("   day         " + " ".join(f"{c[:5]:>5}" for c in cities) + "  total/expected")
    for day, row in table.items():
        print(f"   {day}  " + " ".join(f"{row[c]:>5}" for c in cities) + f"  {sum(row.values())}/{24 * len(cities)}")


def _print_hours(conn):
    print("\n2. COMPLETENESS BY LOCAL HOUR OF DAY (all cities; maximum "
          f"{EXPECTED_PER_HOUR} = {CITY_DAYS} days x {N_CITIES} cities)")
    for hr, n, exp in completeness_by_hour(conn):
        print(f"   {hr:02d}:00  {n:>3}/{exp}  {100 * n / exp:5.1f}%")


def _print_outcomes(conn):
    print("\n3. REQUEST OUTCOMES BY LOCAL DAY AND ENDPOINT")
    print("   day         endpoint      requests    ok  failed  success%  retried  retries")
    for day, ep, req, ok, bad, retried, retries in request_outcomes_by_day(conn):
        print(f"   {day}  {ep:<12} {req:>8} {ok:>5} {bad:>7} {100 * ok / req:>8.1f} {retried:>8} {retries:>8}")


def _print_quarantine(conn):
    total, quarantined_requests, reasons = quarantine_by_reason(conn)
    print("\n4. QUARANTINE BY REASON CODE")

    if not reasons:
        print(
            f"   none quarantined "
            f"(0 of {total} scheduled requests = 0.0%)"
        )
        return

    for code, count in reasons:
        print(f"   {code:<28} {count:>5}")

    rate = 100 * quarantined_requests / total if total else 0.0
    print(
        f"   unique quarantined requests: "
        f"{quarantined_requests} of {total} scheduled requests = {rate:.2f}%"
    )


def _print_latency(conn):
    print("\n5. API LATENCY OF SUCCESSFUL REQUESTS (ms)")
    print("   endpoint        n    min  median   p95    max")
    for ep, n, lo, med, p95, hi in latency_summary(conn):
        if n == 0:
            print(f"   {ep:<12} {n:>5}  (no successful requests)")
        else:
            print(f"   {ep:<12} {n:>5} {lo:>6} {med:>7.0f} {p95:>5} {hi:>6}")


def _print_failures(conn):
    print("\n6. FAILED REQUESTS BY REASON (times are UTC)")
    rows = failures_by_reason(conn)
    if not rows:
        print("   none")
    for ep, http, reason, n, first, last in rows:
        print(f"   {ep:<12} http={http:<4} x{n:<3} {first} .. {last}  {reason}")


QUERIES = {
    "daily": _print_daily, "hours": _print_hours, "outcomes": _print_outcomes,
    "quarantine": _print_quarantine, "latency": _print_latency, "failures": _print_failures,
}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default="data/assessed.db")
    ap.add_argument("--query", choices=sorted(QUERIES), help="run one query (default: all six)")
    args = ap.parse_args(argv)
    if not Path(args.db).exists():
        raise SystemExit(f"database not found: {args.db}")
    conn = open_ro(args.db)
    try:
        for name, fn in QUERIES.items():
            if args.query in (None, name):
                fn(conn)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
