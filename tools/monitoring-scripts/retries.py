# ran from outside the collector clone; copied on 2026-11-16 for the record
import sqlite3, sys, pathlib
c = sqlite3.connect(pathlib.Path(sys.argv[1]).resolve().as_uri() + "?mode=ro", uri=True)
print("successful requests that needed retries:")
for r in c.execute("SELECT run_id, city_id, endpoint, started_at_utc, retry_count, latency_ms, http_status FROM collection_runs WHERE status='success' AND retry_count>0 ORDER BY started_at_utc"): print(r)
print("slowest 5 successful requests:")
for r in c.execute("SELECT run_id, city_id, endpoint, started_at_utc, retry_count, latency_ms FROM collection_runs WHERE status='success' ORDER BY latency_ms DESC LIMIT 5"): print(r)