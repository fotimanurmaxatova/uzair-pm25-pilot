# ran from outside the collector clone; copied on 2026-11-16 for the record
import sqlite3
c = sqlite3.connect(r"file:C:\UzAir_collect\data\assessed.db?mode=ro", uri=True)
rows = c.execute("SELECT r.run_id, ci.name, r.endpoint, r.started_at_utc, r.http_status, r.retry_count, r.latency_ms, r.error_message FROM collection_runs r JOIN cities ci USING(city_id) WHERE r.status<>'success' ORDER BY r.run_id").fetchall()
print(*rows, sep="\n")