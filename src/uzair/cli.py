"""Command line: python -m uzair.cli collect | latest"""
import argparse

from . import collector, db, query


def main(argv=None):
    p = argparse.ArgumentParser(prog="uzair")
    p.add_argument("--db", default=str(db.DEFAULT_DB))
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="poll all cities once")
    c.add_argument("--scheduled", action="store_true",
               help="mark run as scheduled (used by the scheduler). Default is manual.")
    l = sub.add_parser("latest", help="show most recent stored observations")
    l.add_argument("-n", type=int, default=8)
    args = p.parse_args(argv)

    conn = db.connect(args.db)
    db.init_db(conn)
    if args.cmd == "collect":
        for city, outcome in collector.collect_all(conn, is_pilot=0 if args.assessed else 1,
                      mode="scheduled" if args.scheduled else "manual"):
            print(f"{city:<12} {outcome}")
    else:
        for r in query.latest_observations(conn, args.n):
            print(f"{r['name']:<12} valid={r['observation_hour_utc']} recv={r['collected_at_utc']} "
                  f"pm2.5={r['pm2_5']:.1f} wind={r['wind_speed_ms']:.1f}m/s "
                  f"native={r['is_native_step']} pilot={r['is_pilot']}")
    conn.close()


if __name__ == "__main__":
    main()
