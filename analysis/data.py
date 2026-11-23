"""Guarded analysis data layer (decisions 0009 and 0010; issue #17).  Read-only, standard library only.

Rules enforced here, not left to the caller:
  * Only rows with collected_at_utc STRICTLY before the final selection cut-off (6 Nov 17:00Z) are read
    from the database (SQL filter), so no later-received row is ever loaded.
  * A loaded row received at or after that cut-off, or whose valid time is a test origin or later
    (>= 7 Nov 00:00 local), raises GuardError.  Violations stop processing; they are never dropped silently.
  * Simulated prediction time of origin t = the receipt time (collected_at_utc) of the origin row.  All features
    of the origin row are available then.  The lag rows (t-3 h, t-6 h; the 3-hour pressure change uses the t-3 h
    row) must have been received STRICTLY before that prediction time; otherwise the pair is not eligible.
  * A pair (origin t, target t + 6 h) is eligible for a partition only if lags t-3 h, t-6 h and the
    target exist by exact valid time, every feature row was available at the prediction time, and the target
    (and, for fitted partitions, the origin and lag rows) was received strictly before the partition cut-off.
    Pairs that fail this are not eligible.  Those lost only because a feature row arrived too late are listed
    by `unavailable()` and printed, so they are counted, never dropped silently.
  * The test partition cannot be requested: GuardError.

Entry point (prints COUNTS only, never values):
    python -m analysis.data --db snapshots\\assessed_snapshot.db
Synthetic tests:
    python -m pytest tests\\test_analysis_data.py -q
"""
import argparse
import math
from collections import Counter
from datetime import datetime

from analysis import cutoffs as cut
from monitoring.coverage import is_native, open_ro, parse
from monitoring.prepare import FEATURES, _trig

FMT = "%Y-%m-%dT%H:%M:%SZ"


class GuardError(RuntimeError):
    """A decision-0009 rule was violated.  Processing must stop."""


def iso(dt):
    return dt.strftime(FMT)


def load_raw(conn, cutoff=cut.FINAL_CUTOFF_UTC):
    """Scheduled, non-pilot rows received strictly before `cutoff`.  Later rows are never read."""
    conn.row_factory = lambda cur, r: dict(zip([d[0] for d in cur.description], r))
    sel = ", ".join(f"o.{f}" for f in FEATURES)
    return conn.execute(
        f"SELECT c.name AS city, o.observation_hour_utc, o.collected_at_utc, o.weather_time_utc, {sel} "
        "FROM observations o JOIN cities c USING (city_id) "
        "WHERE o.is_pilot=0 AND o.acquisition_mode='scheduled' AND o.collected_at_utc < ? "
        "ORDER BY c.city_id, o.observation_hour_utc", (iso(cutoff),)).fetchall()


def check_raw(raw, cutoff=cut.FINAL_CUTOFF_UTC):
    for r in raw:
        if parse(r["collected_at_utc"]) >= cutoff:
            raise GuardError(f"row received at or after the cut-off {iso(cutoff)}: "
                             f"{r['city']} {r['observation_hour_utc']} received {r['collected_at_utc']}")
        if parse(r["observation_hour_utc"]) >= cut.TEST_START_UTC:
            raise GuardError(f"test-origin row loaded: {r['city']} {r['observation_hour_utc']}")


def build(raw, cutoff=cut.FINAL_CUTOFF_UTC):
    """Guarded: per-row dicts with exact-valid-time lags and target (same derivations as monitoring.prepare)."""
    check_raw(raw, cutoff)
    return derive_rows(raw)


def derive_rows(raw):
    """UNGUARDED row derivation.  Only analysis.evaluate and the post-test modules may call it, and only after
    the freeze guard has passed.  Model selection and the freeze must use `build` / `load_development`."""
    by = {(r["city"], parse(r["observation_hour_utc"])): r for r in raw}
    rows = []
    for (city, t), r in by.items():
        lag3, lag6, tgt = (by.get((city, t + k * cut.H)) for k in (-3, -6, 6))
        lt = (t + cut.TZ).replace(tzinfo=None)
        s, c = _trig(r["wind_direction_deg"])
        p0 = by.get((city, t - 3 * cut.H))
        dp = (r["surface_pressure_hpa"] - p0["surface_pressure_hpa"]) if p0 and None not in (
            r["surface_pressure_hpa"], p0["surface_pressure_hpa"]) else None
        rows.append({
            "city": city, "valid_dt": t, "valid_utc": r["observation_hour_utc"],
            "valid_local": lt.strftime("%Y-%m-%d %H:%M"), "native": int(is_native(t)),
            "receipt_utc": r["collected_at_utc"], "weather_time_utc": r["weather_time_utc"],
            **{f: r[f] for f in FEATURES}, "wind_dir_sin": s, "wind_dir_cos": c, "pressure_change_3h": dp,
            "hour_sin": math.sin(2 * math.pi * lt.hour / 24), "hour_cos": math.cos(2 * math.pi * lt.hour / 24),
            "class_hours": int(lt.weekday() < 5 and 8 <= lt.hour <= 17), "weekday_local": lt.weekday(),
            "high_pm25_35": int(r["pm2_5"] >= 35 if r["pm2_5"] is not None else False),
            "pm25_lag3": lag3["pm2_5"] if lag3 else None, "pm25_lag6": lag6["pm2_5"] if lag6 else None,
            "target_pm25_t6": tgt["pm2_5"] if tgt else None,
            "target_receipt_utc": tgt["collected_at_utc"] if tgt else None,
            "lag3_receipt_utc": lag3["collected_at_utc"] if lag3 else None,
            "lag6_receipt_utc": lag6["collected_at_utc"] if lag6 else None,
            "usable_pair": int(bool(lag3 and lag6 and tgt and tgt["pm2_5"] is not None))})
    return rows


def load_development(conn, cutoff=cut.FINAL_CUTOFF_UTC):
    return build(load_raw(conn, cutoff), cutoff)


def features_available(r):
    """Every feature row (origin t, t-3 h, t-6 h) was received by the prediction time = receipt of the origin row."""
    pt = parse(r["receipt_utc"])
    return all(r[k] is not None and parse(r[k]) < pt for k in ("lag3_receipt_utc", "lag6_receipt_utc"))


def _in_window(r, win, native_only):
    return r["usable_pair"] and (r["native"] or not native_only) and win.first <= r["valid_dt"] <= win.last


def _partition(partition):
    if partition == "test" or partition.startswith("test"):
        raise GuardError("the test partition cannot be requested before the freeze tag")
    return cut.partitions()[partition]


def eligible(rows, partition, native_only=True):
    """Usable pairs of one development partition.  Strict `<` on all receipt-time comparisons."""
    win = _partition(partition)
    out = []
    for r in rows:
        if not _in_window(r, win, native_only):
            continue
        tr = parse(r["target_receipt_utc"])
        if tr >= cut.FINAL_CUTOFF_UTC:
            raise GuardError("a target received at or after the final cut-off was loaded")
        if not features_available(r):
            continue
        if tr < win.cutoff and max(parse(r["receipt_utc"]), parse(r["lag3_receipt_utc"]),
                                   parse(r["lag6_receipt_utc"])) < win.cutoff:
            out.append(r)
    return out


def unavailable(rows, partition, native_only=True):
    """Pairs in the partition window whose features were NOT all available at the prediction time."""
    win = _partition(partition)
    return [r for r in rows if _in_window(r, win, native_only) and not features_available(r)]


def counts(rows):
    return {name: (len(eligible(rows, name, native_only=False)), len(eligible(rows, name, native_only=True)))
            for name in cut.partitions()}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Guarded analysis data layer: prints counts only.")
    ap.add_argument("--db", default="snapshots/assessed_snapshot.db")
    a = ap.parse_args(argv)
    conn = open_ro(a.db)
    try:
        rows = load_development(conn)
    finally:
        conn.close()
    print(f"rows loaded (received before {iso(cut.FINAL_CUTOFF_UTC)}): {len(rows)}   native: "
          f"{sum(r['native'] for r in rows)}")
    print("usable pairs per partition (hourly | native): " + ", ".join(
        f"{n} {h}|{k}" for n, (h, k) in counts(rows).items()))
    print("pairs excluded because a feature row was received after the prediction time (hourly | native): " + ", ".join(
        f"{n} {len(unavailable(rows, n, False))}|{len(unavailable(rows, n, True))}" for n in cut.partitions()))


if __name__ == "__main__":
    main()