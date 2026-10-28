-- UzAir schema, migration 0001 (issue #2)
-- Times are ISO-8601 UTC text, e.g. 2026-11-02T06:00:00Z

CREATE TABLE cities (
    city_id   INTEGER PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE,
    latitude  REAL NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude REAL NOT NULL CHECK (longitude BETWEEN -180 AND 180)
);

CREATE TABLE collector_versions (
    version_id        INTEGER PRIMARY KEY,
    version           TEXT NOT NULL UNIQUE,
    git_commit        TEXT,
    registered_at_utc TEXT NOT NULL
);

-- One row per API request (city x endpoint): audit log of every attempt.
CREATE TABLE collection_runs (
    run_id               INTEGER PRIMARY KEY,
    city_id              INTEGER NOT NULL REFERENCES cities(city_id),
    endpoint             TEXT NOT NULL CHECK (endpoint IN ('weather', 'air_quality')),
    started_at_utc       TEXT NOT NULL,
    http_status          INTEGER,
    latency_ms           INTEGER CHECK (latency_ms >= 0),
    retry_count          INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    status               TEXT NOT NULL
                         CHECK (status IN ('success', 'failed', 'rejected', 'quarantined')),
    error_message        TEXT,
    collector_version_id INTEGER NOT NULL REFERENCES collector_versions(version_id),
    acquisition_mode     TEXT NOT NULL DEFAULT 'scheduled'
                         CHECK (acquisition_mode IN ('scheduled', 'manual')),
    is_pilot             INTEGER NOT NULL DEFAULT 1 CHECK (is_pilot IN (0, 1))
);

-- Original response, never modified (provenance).
CREATE TABLE raw_responses (
    raw_id          INTEGER PRIMARY KEY,
    run_id          INTEGER NOT NULL UNIQUE REFERENCES collection_runs(run_id),
    received_at_utc TEXT NOT NULL,
    response_sha256 TEXT NOT NULL CHECK (length(response_sha256) = 64),
    body            TEXT NOT NULL
);

-- One row = one city + one air-quality valid time (decision 0002).
CREATE TABLE observations (
    obs_id               INTEGER PRIMARY KEY,
    city_id              INTEGER NOT NULL REFERENCES cities(city_id),
    observation_hour_utc TEXT NOT NULL,   -- air-quality valid time
    weather_time_utc     TEXT NOT NULL,   -- weather valid time
    collected_at_utc     TEXT NOT NULL,   -- receipt time
    weather_run_id       INTEGER NOT NULL REFERENCES collection_runs(run_id),
    aq_run_id            INTEGER NOT NULL REFERENCES collection_runs(run_id),

    temperature_2m       REAL CHECK (temperature_2m BETWEEN -60 AND 60),
    relative_humidity_2m REAL CHECK (relative_humidity_2m BETWEEN 0 AND 100),
    precipitation_mm     REAL CHECK (precipitation_mm >= 0),
    wind_speed_ms        REAL NOT NULL CHECK (wind_speed_ms >= 0),
    wind_direction_deg   REAL CHECK (wind_direction_deg BETWEEN 0 AND 360),
    surface_pressure_hpa REAL CHECK (surface_pressure_hpa BETWEEN 700 AND 1100),
    pm2_5                REAL NOT NULL CHECK (pm2_5 BETWEEN 0 AND 1000),
    pm10                 REAL CHECK (pm10 BETWEEN 0 AND 1000),
    nitrogen_dioxide     REAL CHECK (nitrogen_dioxide >= 0),
    ozone                REAL CHECK (ozone >= 0),

    wind_speed_unit      TEXT NOT NULL CHECK (wind_speed_unit = 'm/s'),
    aq_domain            TEXT NOT NULL,
    aq_interval_s        INTEGER NOT NULL,
    weather_interval_s   INTEGER NOT NULL,
    is_native_step       INTEGER NOT NULL CHECK (is_native_step IN (0, 1)),
    acquisition_mode     TEXT NOT NULL DEFAULT 'scheduled'
                         CHECK (acquisition_mode IN ('scheduled', 'manual')),
    is_pilot             INTEGER NOT NULL DEFAULT 1 CHECK (is_pilot IN (0, 1)),
    quality_flag         TEXT,

    UNIQUE (city_id, observation_hour_utc),
    CHECK (pm10 IS NULL OR pm2_5 <= pm10)
);

CREATE TABLE quarantine (
    quarantine_id      INTEGER PRIMARY KEY,
    run_id             INTEGER NOT NULL REFERENCES collection_runs(run_id),
    reason_code        TEXT NOT NULL,
    detail             TEXT,
    quarantined_at_utc TEXT NOT NULL
);

CREATE INDEX idx_obs_hour       ON observations(observation_hour_utc);
CREATE INDEX idx_runs_started   ON collection_runs(started_at_utc);
CREATE INDEX idx_quarantine_why ON quarantine(reason_code);