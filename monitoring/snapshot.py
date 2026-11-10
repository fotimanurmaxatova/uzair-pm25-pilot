"""Create the lawful data snapshot required in the final commit (read-only on the source database).

Writes into --out: assessed_snapshot.db (SQLite online-backup copy), CSV exports of the audit tables
(raw response bodies stay inside the .db), collection log copy, MANIFEST.json (SHA-256 of every file,
row counts, window, attribution) and ATTRIBUTION.md. Verifies every raw-response hash first.
No personal data are involved. Usage:
  python -m monitoring.snapshot --db C:\\UzAir_collect\\data\\assessed.db --log C:\\UzAir_collect\\logs\\assessed.log --out snapshots
"""
import argparse
import csv
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from monitoring.coverage import open_ro

TABLES = ("cities", "collector_versions", "collection_runs", "observations", "quarantine")
ATTRIBUTION = ("Weather data by Open-Meteo.com (CC BY 4.0), https://open-meteo.com/. Air-quality data are CAMS "
               "global model output distributed through the Open-Meteo Air Quality API. Collected by the UzAir "
               "collector between 2026-11-02 00:05 and 2026-11-08 23:05 (Asia/Tashkent).\n")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def make_snapshot(db, out, log=None, now=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    src = open_ro(db)
    src.row_factory = sqlite3.Row
    bad = [r["run_id"] for r in src.execute("SELECT run_id, body, response_sha256 FROM raw_responses")
           if hashlib.sha256(r["body"].encode("utf-8")).hexdigest() != r["response_sha256"]]
    if bad:
        raise SystemExit(f"raw-response hash mismatches for runs {bad[:10]}: snapshot refused")
    dst = sqlite3.connect(out / "assessed_snapshot.db")
    src.backup(dst)
    dst.close()
    counts = {}
    for t in TABLES:
        cur = src.execute(f"SELECT * FROM {t}")
        cols = [d[0] for d in cur.description]
        n = 0
        with open(out / f"{t}.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(cols)
            for r in cur:
                w.writerow(["" if v is None else v for v in tuple(r)])
                n += 1
        counts[t] = n
    counts["raw_responses (inside the .db only)"] = src.execute("SELECT COUNT(*) FROM raw_responses").fetchone()[0]
    counts["observations_valid_primary"] = src.execute(
        "SELECT COUNT(*) FROM observations WHERE is_pilot=0 AND acquisition_mode='scheduled'").fetchone()[0]
    src.close()
    if log and Path(log).exists():
        shutil.copyfile(log, out / "collection_log.txt")
    (out / "ATTRIBUTION.md").write_text(ATTRIBUTION, encoding="utf-8")
    files = sorted(p for p in out.iterdir() if p.is_file() and p.name != "MANIFEST.json")
    manifest = {"created_utc": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source_database_name": Path(db).name, "row_counts": counts,
                "raw_hash_check": "all raw responses re-hashed, 0 mismatches",
                "files_sha256": {p.name: sha256_file(p) for p in files}}
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default="data/assessed.db")
    ap.add_argument("--log")
    ap.add_argument("--out", default="snapshots")
    a = ap.parse_args(argv)
    m = make_snapshot(a.db, a.out, a.log)
    print(json.dumps(m, indent=2))


if __name__ == "__main__":
    main()
