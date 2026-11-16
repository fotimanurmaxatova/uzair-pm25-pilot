# ran from outside the collector clone; copied on 2026-11-16 for the record
import sqlite3, sys
db = sys.argv[1] if len(sys.argv) > 1 else r"C:\UzAir_collect\data\assessed.db"
c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)

def show(title, sql):
    print(f"\n== {title}")
    for r in c.execute(sql).fetchall():
        print("  ", r)

show("Runs by pilot/status", "SELECT is_pilot, acquisition_mode, status, COUNT(*) FROM collection_runs GROUP BY 1,2,3")
show("Polls per hour (UTC): runs, success", "SELECT substr(started_at_utc,1,13) h, COUNT(*), SUM(status='success') FROM collection_runs GROUP BY h ORDER BY h")
show("Per city: rows, native rows, first, last valid time", "SELECT c.name, COUNT(*), SUM(is_native_step), MIN(observation_hour_utc), MAX(observation_hour_utc) FROM observations o JOIN cities c USING(city_id) GROUP BY c.name")
show("Quarantine reasons", "SELECT reason_code, COUNT(*) FROM quarantine GROUP BY 1")
show("Rejected/failed runs", "SELECT endpoint, error_message, COUNT(*) FROM collection_runs WHERE status IN ('rejected','failed') GROUP BY 1,2")
show("Latency ms (avg, max) and runs with retries", "SELECT ROUND(AVG(latency_ms)), MAX(latency_ms), SUM(retry_count>0) FROM collection_runs")
show("Valid-time gap AQ vs weather > 30 min", "SELECT COUNT(*) FROM observations WHERE abs(strftime('%s',observation_hour_utc)-strftime('%s',weather_time_utc))>1800")
show("PM2.5 range per city (min, avg, max)", "SELECT c.name, MIN(pm2_5), ROUND(AVG(pm2_5),1), MAX(pm2_5) FROM observations o JOIN cities c USING(city_id) GROUP BY c.name")
show("Collector versions used", "SELECT cv.version, COUNT(*) FROM collection_runs r JOIN collector_versions cv ON cv.version_id=r.collector_version_id GROUP BY 1")
print("\nTotal observations:", c.execute("SELECT COUNT(*) FROM observations").fetchone()[0])