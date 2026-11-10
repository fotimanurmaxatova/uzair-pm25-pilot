"""Cleaning / transformation step: assessed database -> analysis-ready rows (read-only).

Output: one CSV row per VALID assessed observation (scheduled, is_pilot=0). Original values are never
changed; derived columns are added. Primary analysis = rows with native=1 (UTC valid hour divisible by 3);
sensitivity = all rows. Lags and the six-hour target are matched by EXACT valid time (same city); a missing
match stays empty (no next-row substitution). Partition tags follow docs/protocol/analysis-protocol.md.

Prints COUNTS only (never values), so running it is not "looking at" test outcomes.
Usage:  python -m monitoring.prepare --db C:\\UzAir_collect\\data\\assessed.db --out derived\\analysis_rows.csv
"""
import argparse
import csv
import math
from collections import Counter
from pathlib import Path

from monitoring.coverage import H, TZ, is_native, loc, open_ro, parse, partitions  # one source of truth

FEATURES = ["temperature_2m", "relative_humidity_2m", "precipitation_mm", "wind_speed_ms", "wind_direction_deg",
            "surface_pressure_hpa", "pm2_5", "pm10", "nitrogen_dioxide", "ozone"]
COLUMNS = (["city", "valid_utc", "valid_local", "native", "receipt_utc", "weather_time_utc"] + FEATURES +
           ["wind_dir_sin", "wind_dir_cos", "pressure_change_3h", "hour_sin", "hour_cos", "class_hours",
            "weekday_local", "high_pm25_35", "pm25_lag3", "pm25_lag6", "target_pm25_t6", "target_receipt_utc",
            "usable_pair", "partitions"])


def _trig(deg):
    return (None, None) if deg is None else (math.sin(math.radians(deg)), math.cos(math.radians(deg)))


def build(conn):
    conn.row_factory = lambda cur, r: dict(zip([d[0] for d in cur.description], r))
    sel = ", ".join(f"o.{f}" for f in FEATURES)
    raw = conn.execute(f"SELECT c.name AS city, o.observation_hour_utc, o.collected_at_utc, o.weather_time_utc, {sel} "
                       "FROM observations o JOIN cities c USING (city_id) "
                       "WHERE o.is_pilot=0 AND o.acquisition_mode='scheduled' ORDER BY c.city_id, o.observation_hour_utc").fetchall()
    by = {(r["city"], parse(r["observation_hour_utc"])): r for r in raw}
    parts, rows = partitions(), []
    for (city, t), r in by.items():
        lag3, lag6, tgt = (by.get((city, t + k * H)) for k in (-3, -6, 6))
        lt = loc(t)
        s, c = _trig(r["wind_direction_deg"])
        p0 = by.get((city, t - 3 * H))
        dp = (r["surface_pressure_hpa"] - p0["surface_pressure_hpa"]) if p0 and None not in (
            r["surface_pressure_hpa"], p0["surface_pressure_hpa"]) else None
        usable = bool(lag3 and lag6 and tgt)
        tags = []
        if usable:
            tr = loc(parse(tgt["collected_at_utc"]))
            tags = [n for n, (a, b, cut) in parts.items() if a <= lt <= b and (cut is None or tr <= cut)]
        rows.append({
            "city": city, "valid_utc": r["observation_hour_utc"], "valid_local": lt.strftime("%Y-%m-%d %H:%M"),
            "native": int(is_native(t)), "receipt_utc": r["collected_at_utc"], "weather_time_utc": r["weather_time_utc"],
            **{f: r[f] for f in FEATURES}, "wind_dir_sin": s, "wind_dir_cos": c, "pressure_change_3h": dp,
            "hour_sin": math.sin(2 * math.pi * lt.hour / 24), "hour_cos": math.cos(2 * math.pi * lt.hour / 24),
            "class_hours": int(lt.weekday() < 5 and 8 <= lt.hour <= 17), "weekday_local": lt.weekday(),
            "high_pm25_35": int(r["pm2_5"] >= 35),
            "pm25_lag3": lag3["pm2_5"] if lag3 else None, "pm25_lag6": lag6["pm2_5"] if lag6 else None,
            "target_pm25_t6": tgt["pm2_5"] if tgt else None,
            "target_receipt_utc": tgt["collected_at_utc"] if tgt else None,
            "usable_pair": int(usable), "partitions": "|".join(tags)})
    return rows


def write_csv(rows, out):
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows({k: ("" if v is None else v) for k, v in r.items()} for r in rows)


def summary(rows):
    out = [f"rows: {len(rows)}   native (primary): {sum(r['native'] for r in rows)}   usable pairs (hourly/native): "
           f"{sum(r['usable_pair'] for r in rows)}/{sum(r['usable_pair'] for r in rows if r['native'])}"]
    cnt = {"hourly": Counter(), "native": Counter()}
    for r in rows:
        for p in filter(None, r["partitions"].split("|")):
            cnt["hourly"][p] += 1
            if r["native"]:
                cnt["native"][p] += 1
    out.append("usable pairs per partition (hourly | native): " + ", ".join(
        f"{p} {cnt['hourly'][p]}|{cnt['native'][p]}" for p in partitions()))
    miss = {k: sum(1 for r in rows if r[k] is None) for k in FEATURES + ["pressure_change_3h", "wind_dir_sin"]}
    out.append("missing values per column (counts): " + ", ".join(f"{k} {v}" for k, v in miss.items() if v) or "none")
    if not any(miss.values()):
        out[-1] = "missing values per column: none"
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default="data/assessed.db")
    ap.add_argument("--out", default="derived/analysis_rows.csv")
    a = ap.parse_args(argv)
    conn = open_ro(a.db)
    rows = build(conn)
    conn.close()
    write_csv(rows, a.out)
    print(summary(rows))
    print(f"written: {a.out}")


if __name__ == "__main__":
    main()
