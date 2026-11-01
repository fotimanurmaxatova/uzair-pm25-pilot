"""Command line: python -m uzair.cli collect | latest | provenance | verify | status"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import collector, db, guards, query

ASSESSED_DB = db.ROOT / "data" / "assessed.db"


def main(argv=None, now=None):
    p = argparse.ArgumentParser(prog="uzair")
    p.add_argument("--db", default=None,
                   help="database file (default: data/uzair.db, or data/assessed.db with --assessed)")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="poll all cities once")
    c.add_argument("--assessed", action="store_true",
                   help="store as assessed data (is_pilot=0). Default is a development run (is_pilot=1).")
    c.add_argument("--scheduled", action="store_true",
                   help="mark the run as scheduled (used by the scheduler). Default is manual.")
    l = sub.add_parser("latest", help="show most recent stored observations")
    l.add_argument("-n", type=int, default=8)
    v = sub.add_parser("provenance", help="show the audit trail (runs, status, latency, hashes) behind recent rows")
    v.add_argument("-n", type=int, default=8)
    sub.add_parser("verify", help="recompute SHA-256 of every stored raw response")
    sub.add_parser("status", help="row and run counts by pilot flag")
    args = p.parse_args(argv)

    if args.cmd == "collect" and args.assessed:
        try:
            guards.check_assessed_allowed(now or datetime.now(timezone.utc), args.scheduled,
                                          collector.current_version()[0])
        except guards.GuardError as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 2
        db_path = args.db or str(ASSESSED_DB)
    else:
        db_path = args.db or str(db.DEFAULT_DB)

    conn = db.connect(db_path)
    db.init_db(conn)
    code = 0
    if args.cmd == "collect":
        results = collector.collect_all(
            conn,
            is_pilot=0 if args.assessed else 1,
            mode="scheduled" if args.scheduled else "manual",
        )
        for city, outcome in results.items():
            print(f"{city:<12} {outcome}")
    elif args.cmd == "latest":
        for r in query.latest_observations(conn, args.n):
            print(f"{r['name']:<12} valid={r['observation_hour_utc']} recv={r['collected_at_utc']} "
                  f"pm2.5={r['pm2_5']:.1f} wind={r['wind_speed_ms']:.1f}m/s "
                  f"native={r['is_native_step']} pilot={r['is_pilot']}")
    elif args.cmd == "provenance":
        for r in query.provenance(conn, args.n):
            print(f"obs {r['obs_id']} {r['name']} valid={r['observation_hour_utc']} recv={r['collected_at_utc']} "
                  f"mode={r['acquisition_mode']} pilot={r['is_pilot']} v={r['collector_version']}\n"
                  f"  weather run {r['w_run']} http={r['w_http']} {r['w_ms']}ms retry={r['w_retry']} "
                  f"model={r['weather_model']} sha256={r['w_sha'][:16]}\n"
                  f"  air-qual run {r['a_run']} http={r['a_http']} {r['a_ms']}ms retry={r['a_retry']} "
                  f"domain={r['aq_domain']} sha256={r['a_sha'][:16]}")
    elif args.cmd == "verify":
        checked, bad = query.verify_raw_hashes(conn)
        print(f"checked {checked} raw responses, {len(bad)} hash mismatches")
        if bad:
            print("mismatching run_ids:", bad)
            code = 1
    elif args.cmd == "status":
        obs, runs = query.counts(conn)
        for r in obs:
            print(f"observations is_pilot={r['is_pilot']}: {r['n']}")
        for r in runs:
            print(f"runs is_pilot={r['is_pilot']} status={r['status']}: {r['n']}")
    conn.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
