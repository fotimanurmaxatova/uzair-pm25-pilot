"""Read-back queries."""


def latest_observations(conn, limit=8):
    return conn.execute(
        "SELECT c.name, o.observation_hour_utc, o.collected_at_utc, o.pm2_5, o.wind_speed_ms,"
        " o.is_native_step, o.is_pilot FROM observations o JOIN cities c USING (city_id)"
        " ORDER BY o.obs_id DESC LIMIT ?", (limit,)).fetchall()
