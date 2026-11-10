"""Post-hoc quality audit of the assessed database (read-only).

The collector is frozen, so the stale / location-echo / large-jump checks promised in the approval request
run HERE, on the stored data and raw responses, and are reported, not applied by deleting anything.
Also answers the approval-request promise: do the eight cities really return different grid cells, and
are any two cities' series (near-)identical?

Prints counts and city names, not individual values. Series similarity only uses valid times BEFORE
`--before` (default: start of the test window, 7 Nov 00:00 Tashkent) so the test period is not inspected.
Usage:  python -m monitoring.audit --db C:\\UzAir_collect\\data\\assessed.db
"""
import argparse
import json
from collections import defaultdict
from datetime import timedelta
from itertools import combinations

from monitoring.coverage import H, loc, open_ro, parse

TEST_START_UTC = "2026-11-06T19:00:00Z"      # Sat 7 Nov 00:00 Asia/Tashkent
TOL_DEG, STALE_H, JUMP = 0.5, 2, 100


def audit(conn, before=TEST_START_UTC):
    conn.row_factory = lambda cur, r: dict(zip([d[0] for d in cur.description], r))
    L, p = [], None
    p = L.append
    obs = conn.execute("SELECT c.name city, o.* FROM observations o JOIN cities c USING (city_id) "
                       "WHERE o.is_pilot=0 AND o.acquisition_mode='scheduled' ORDER BY c.city_id, o.observation_hour_utc").fetchall()
    pilots = conn.execute("SELECT COUNT(*) n FROM observations WHERE is_pilot=1").fetchone()["n"]
    p(f"rows audited: {len(obs)} (pilot rows present in this database: {pilots})")

    stale_w = [o for o in obs if parse(o["collected_at_utc"]) - parse(o["weather_time_utc"]) > timedelta(hours=STALE_H)]
    stale_a = [o for o in obs if parse(o["collected_at_utc"]) - parse(o["observation_hour_utc"]) > timedelta(hours=STALE_H)]
    lag_w = max((parse(o["collected_at_utc"]) - parse(o["weather_time_utc"])).total_seconds() / 60 for o in obs) if obs else 0
    lag_a = max((parse(o["collected_at_utc"]) - parse(o["observation_hour_utc"])).total_seconds() / 60 for o in obs) if obs else 0
    p(f"\n1. STALE (receipt more than {STALE_H} h after valid time): weather {len(stale_w)}, air quality {len(stale_a)}"
      f"   (largest receipt lag: weather {lag_w:.0f} min, air quality {lag_a:.0f} min)")

    by_city = defaultdict(dict)
    for o in obs:
        by_city[o["city"]][parse(o["observation_hour_utc"])] = o
    jumps = [(c, loc(t)) for c, d in by_city.items() for t, o in d.items()
             if t - H in d and abs(o["pm2_5"] - d[t - H]["pm2_5"]) > JUMP]
    p(f"\n2. LARGE HOURLY JUMPS (|change in PM2.5| > {JUMP} ug/m3 between consecutive hours): {len(jumps)}"
      + "".join(f"\n   {c} at {t:%a %d %b %H:%M} local" for c, t in jumps[:20]))
    flags = conn.execute("SELECT quality_flag, COUNT(*) n FROM observations WHERE quality_flag IS NOT NULL GROUP BY 1").fetchall()
    p(f"   rows with a quality_flag: {sum(f['n'] for f in flags)}")

    cells, bad_echo = defaultdict(set), []
    for r in conn.execute("SELECT c.name city, c.latitude lat, c.longitude lon, r.endpoint ep, x.body "
                          "FROM raw_responses x JOIN collection_runs r USING (run_id) JOIN cities c USING (city_id) "
                          "WHERE r.is_pilot=0 AND r.status='success'"):
        try:
            d = json.loads(r["body"])
            glat, glon = float(d["latitude"]), float(d["longitude"])
        except (ValueError, KeyError, TypeError):
            continue
        cells[(r["ep"], r["city"])].add((round(glat, 4), round(glon, 4)))
        if abs(glat - r["lat"]) > TOL_DEG or abs(glon - r["lon"]) > TOL_DEG:
            bad_echo.append((r["city"], r["ep"]))
    p(f"\n3. LOCATION ECHO (grid more than {TOL_DEG} deg from the city point): {len(bad_echo)} responses"
      + "".join(f"\n   {c} {e}" for c, e in sorted(set(bad_echo))[:10]))

    p("\n4. GRID CELLS PER CITY (distinct cells echoed by the API)")
    for ep in ("weather", "air_quality"):
        owners = defaultdict(list)
        for (e, c), cs in cells.items():
            if e == ep:
                for cell in cs:
                    owners[cell].append(c)
        shared = {k: v for k, v in owners.items() if len(set(v)) > 1}
        p(f"   {ep}: {len(owners)} distinct cells for {len({c for (e, c) in cells if e == ep})} cities; shared cells: "
          + (", ".join(f"{k} <- {sorted(set(v))}" for k, v in shared.items()) if shared else "none"))

    p(f"\n5. SERIES SIMILARITY before {before} (share of identical stored values at the same valid time)")
    flagged = False
    for var, label in (("pm2_5", "PM2.5"), ("temperature_2m", "temperature")):
        for a, b in combinations(by_city, 2):
            common = [t for t in by_city[a] if t in by_city[b] and t.strftime("%Y-%m-%dT%H:%M:%SZ") < before
                      and by_city[a][t][var] is not None and by_city[b][t][var] is not None]
            if len(common) >= 24:
                same = sum(by_city[a][t][var] == by_city[b][t][var] for t in common) / len(common)
                if same >= 0.5:
                    flagged = True
                    p(f"   !! {a} / {b} {label}: {100 * same:.0f}% identical over {len(common)} common hours")
    if not flagged:
        p("   no city pair has >= 50% identical values (checked PM2.5 and temperature, pairs with >= 24 common hours)")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default="data/assessed.db")
    ap.add_argument("--before", default=TEST_START_UTC)
    a = ap.parse_args(argv)
    conn = open_ro(a.db)
    print(audit(conn, a.before))
    conn.close()


if __name__ == "__main__":
    main()
