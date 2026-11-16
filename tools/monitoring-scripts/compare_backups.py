# ran from outside the collector clone; copied on 2026-11-16 for the record
import sqlite3, sys, pathlib
q = lambda p, s: sqlite3.connect(pathlib.Path(p).resolve().as_uri() + "?mode=ro", uri=True).execute(s).fetchone()
for p in sys.argv[1:]: print(p, "observations/first/last:", q(p, "SELECT COUNT(*), MIN(collected_at_utc), MAX(collected_at_utc) FROM observations"), "runs:", q(p, "SELECT COUNT(*), MAX(started_at_utc) FROM collection_runs"))