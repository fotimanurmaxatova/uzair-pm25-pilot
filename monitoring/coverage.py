"""Read-only coverage and forecast-eligibility report for the assessed collection.

Answers the Module Leader's reporting requirements (email on coverage, Nov 2026):
  * valid primary city-hour rows vs 1,344 and vs elapsed scheduled city-hours
  * run outcomes per hourly poll: complete / partial / failed / missed, with reasons
  * coverage by city and day, longest gaps, native three-hourly rows
  * usable EXACT t -> t+6 h pairs (matched by valid time) per partition of the approved calendar

Never writes to the database (opened read-only). Lives outside src/ so that adding it does not
change the frozen collector. Usage:  python -m monitoring.coverage [--db data/assessed.db] [--now ISO]
"""
import argparse
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

UTC = timezone.utc
TZ = timedelta(hours=5)                              # Asia/Tashkent, no DST
START = datetime(2026, 11, 1, 19, 0, tzinfo=UTC)     # first scheduled slot = Mon 2 Nov 00:00 local
N_SLOTS, N_CITIES, TARGET = 168, 8, 1000
H = timedelta(hours=1)


def parse(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def loc(dt):
    return (dt + TZ).replace(tzinfo=None)


def is_native(dt):
    return dt.hour % 3 == 0 and dt.minute == 0       # CAMS global grid (UTC), not "every third row"


def _L(day, hour=0):
    return datetime(2026, 11, day, hour)             # local (Asia/Tashkent) naive time


def partitions():
    """name -> (first origin, last origin, fitting cut-off or None), all local times (protocol calendar)."""
    p = {"train_final": (_L(2, 0), _L(6, 15), _L(6, 22))}
    for k, day in enumerate((4, 5, 6), 1):
        v0 = _L(day, 0)
        p[f"cv{k}_train"] = (_L(2, 0), v0 - timedelta(hours=7), v0)
        p[f"cv{k}_valid"] = (v0, _L(day, 15), None)
    p["test"] = (_L(7, 0), _L(8, 17), None)
    return p


def usable_pairs(obs, native_only):
    """obs: {valid_dt: collected_dt} for ONE city. Return {partition: count} of origins t where
    t, t-3h, t-6h and t+6h all exist (exact valid time) and, for fitted partitions, the outcome
    was RECEIVED by the fitting cut-off. Missing outcomes stay missing (no next-row substitution)."""
    out = Counter()
    for t in obs:
        if native_only and not is_native(t):
            continue
        need = (t - 3 * H, t - 6 * H, t + 6 * H)
        if not all(n in obs for n in need):
            continue
        for name, (a, b, cutoff) in partitions().items():
            if not (a <= loc(t) <= b):
                continue
            if cutoff is not None and loc(obs[t + 6 * H]) > cutoff:
                continue
            out[name] += 1
    return out


def open_ro(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def load(conn):
    conn.row_factory = sqlite3.Row
    obs = defaultdict(dict)
    for r in conn.execute("SELECT c.name, o.observation_hour_utc v, o.collected_at_utc c FROM observations o "
                          "JOIN cities c USING (city_id) WHERE o.is_pilot=0 AND o.acquisition_mode='scheduled'"):
        obs[r["name"]][parse(r["v"])] = parse(r["c"])
    runs = defaultdict(list)
    for r in conn.execute("SELECT started_at_utc s, endpoint, status, error_message e, http_status h "
                          "FROM collection_runs WHERE is_pilot=0 AND acquisition_mode='scheduled'"):
        runs[parse(r["s"]).replace(minute=0, second=0)].append(r)
    cities = [r["name"] for r in conn.execute("SELECT name FROM cities ORDER BY city_id")]
    return cities, obs, runs


def theoretical():
    """Maximum pairs per city per partition if no poll is ever missing: {False: hourly, True: native}."""
    full = {START + k * H: START + k * H + timedelta(minutes=5) for k in range(N_SLOTS)}
    return {native: usable_pairs(full, native) for native in (False, True)}


def report(conn, now=None):
    cities, obs, runs = load(conn)
    now = now or datetime.now(UTC)
    elapsed = min(N_SLOTS, max(0, int((now - START - timedelta(minutes=5)) / H) + 1))
    slots = [START + k * H for k in range(elapsed)]
    n_rows = sum(len(v) for v in obs.values())
    n_elapsed_rows = sum(1 for c in cities for s in slots if s in obs[c])
    L = []
    p = L.append
    p(f"Report time {now:%Y-%m-%d %H:%M}Z ({loc(now):%a %d %b %H:%M} Tashkent)   elapsed polls: {elapsed}/{N_SLOTS}")
    p("\n1. VALID PRIMARY ROWS (scheduled, is_pilot=0)")
    p(f"   {n_rows} of {N_SLOTS * N_CITIES} possible = {100 * n_rows / (N_SLOTS * N_CITIES):.1f}%   (approved target >= {TARGET})")
    if elapsed:
        rate = n_elapsed_rows / (elapsed * N_CITIES)
        p(f"   vs elapsed scheduled city-hours: {n_elapsed_rows} of {elapsed * N_CITIES} = {100 * rate:.1f}%")
        proj = n_elapsed_rows + (N_SLOTS - elapsed) * N_CITIES * rate
        p(f"   projection if the observed rate holds: about {proj:.0f} rows at the end "
          f"({'above' if proj >= TARGET else 'BELOW'} the {TARGET} target)")

    p("\n2. RUN OUTCOMES PER HOURLY POLL (complete = all 8 cities stored)")
    status, bad = Counter(), []
    for s in slots:
        n_obs = sum(1 for c in cities if s in obs[c])
        rs = runs.get(s, [])
        st = "missed" if not rs else "complete" if n_obs == len(cities) else "failed" if n_obs == 0 else "partial"
        status[st] += 1
        if st != "complete":
            why = Counter(f"{r['endpoint']} {r['status']} {r['e'] or r['h'] or ''}".strip() for r in rs if r["status"] != "success")
            bad.append(f"   {loc(s):%a %d %b %H:%M} local  {st:<8} rows {n_obs}/{len(cities)}  "
                       f"{'; '.join(f'{k} x{v}' for k, v in why.items()) or 'no runs recorded (cause unknown)'}")
    p("   " + ", ".join(f"{k} {status[k]}" for k in ("complete", "partial", "failed", "missed")))
    L.extend(bad)

    p("\n3. COVERAGE BY CITY (hourly rows / native 3-hourly rows) AND LONGEST GAP")
    nat_slots = [s for s in slots if is_native(s)]
    for c in cities:
        gap = best = 0
        gstart = bstart = None
        for s in slots:
            if s in obs[c]:
                gap, gstart = 0, None
            else:
                gstart = gstart or s
                gap += 1
                if gap > best:
                    best, bstart = gap, gstart
        nat = sum(1 for s in nat_slots if s in obs[c])
        p(f"   {c:<10} {sum(1 for s in slots if s in obs[c]):>3}/{elapsed}   native {nat:>2}/{len(nat_slots)}   "
          f"longest gap {best} h" + (f" from {loc(bstart):%a %d %b %H:%M}" if best else ""))

    p("\n4. ROWS BY LOCAL DAY (all cities)")
    day = Counter(loc(s).date() for s in slots for c in cities if s in obs[c])
    exp = Counter(loc(s).date() for s in slots for _ in cities)
    for d in sorted(exp):
        p(f"   {d:%a %d %b}  {day[d]:>3}/{exp[d]}")

    p("\n5. USABLE EXACT t -> t+6 h PAIRS (needs t, t-3h, t-6h, t+6h; fitted partitions need outcome received by cut-off)")
    full = theoretical()
    p(f"   {'partition':<12} {'hourly':>13} {'native 3-hourly':>18}      (collected / maximum if nothing is missing)")
    for name in partitions():
        h = sum(usable_pairs(obs[c], False)[name] for c in cities)
        n = sum(usable_pairs(obs[c], True)[name] for c in cities)
        p(f"   {name:<12} {h:>5}/{full[False][name] * len(cities):<7} {n:>8}/{full[True][name] * len(cities):<8}")
    p("   Not yet counted: missing weather/NO2 values after lag construction (report in the analysis step).")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default="data/assessed.db")
    ap.add_argument("--now", help="ISO UTC time for the report, e.g. 2026-11-04T07:00:00Z")
    a = ap.parse_args(argv)
    conn = open_ro(a.db)
    print(report(conn, parse(a.now) if a.now else None))
    conn.close()


if __name__ == "__main__":
    main()
