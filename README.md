# uzair-pm25-pilot
UzAir: Predicting Modelled PM2.5 from Weather in Uzbek Cities (UDE5014CM CW2)

# uzair-pm25-pilot

UzAir: Predicting Modelled PM2.5 from Weather in Uzbek Cities (UDE5014CM CW2)

A seven-day exploratory pilot (approved 2026-10-28, collection from
2 November 2026). It collects weather (Open-Meteo forecast API) and modelled
PM2.5 and related pollutants (Open-Meteo air-quality API, CAMS global domain)
for eight Uzbek cities into a local SQLite database, with validation,
provenance and an audit trail. The target is the API's later modelled PM2.5
estimate, not a measured concentration or a health-safety judgement.

## Status

Checkpoint 1 (MVP): one working collection path with validation, provenance,
SQLite storage and read-back, plus automated tests.
Planned: scheduler, monitoring, analysis (Q1 to Q5), report.

## Requirements

Python 3.10 or newer (developed on 3.12, Windows). Internet access for the
live collection; the tests use fake responses and need no network.

## Clean install (Windows)

```
git clone https://github.com/fotimanurmaxatova/uzair-pm25-pilot.git
cd uzair-pm25-pilot
python -m venv .venv
.venv\Scripts\activate
pip install -e .
pip install pytest
```

## Run the tests

```
python -m pytest -v
```

Expected: all tests pass (schema, validation and collector tests).

## Collect and read back

```
python -m uzair.cli collect
python -m uzair.cli latest
python -m uzair.cli latest -n 16
```

- `collect` polls all eight cities once (weather + air quality). The database
  `data/uzair.db` and its tables are created automatically from `migrations/`.
- By default rows are stored as development data (`is_pilot=1`). Assessed
  collection needs the explicit flag `collect --assessed` (`is_pilot=0`).
- Use `--db data/dev.db` to keep development runs in a separate file.

## How the data is handled

- Requests ask explicitly for `wind_speed_unit=ms`, `timeformat=unixtime` and
  `timezone=GMT`; the response unit is checked (km/h is rejected).
- Valid time (`observation_hour_utc`, `weather_time_utc`) and receipt time
  (`collected_at_utc`) are stored separately. All times are UTC (ISO 8601).
- The original response body and its SHA-256 are stored unchanged in
  `raw_responses`; every request is logged in `collection_runs`.
- Invalid responses go to `quarantine` with a reason code instead of
  `observations`. Duplicates (same city and valid time) are rejected, never
  overwritten.
- Transient failures (timeouts, HTTP 429/5xx) are retried with exponential
  backoff (2, 4, 8 s); other 4xx errors are not retried.
- CAMS global is natively three-hourly, so hourly polling does not create
  independent hourly measurements. `is_native_step=1` marks valid times on
  3-hourly UTC boundaries; the analysis is restricted to those rows.

## Project structure

```
src/uzair/        collector, validation, database, queries, CLI
migrations/       SQL schema and city seed (applied in order)
tests/            automated tests; tests/fixtures/ holds fake API responses
docs/decisions/   decision records (API parameters, time alignment)
docs/approval/    written approval record
docs/ai/          AI-use log
data/             SQLite databases (not committed)
```

## Documentation

- `docs/decisions/0001-api-parameters.md`
- `docs/decisions/0002-time-alignment.md`
- `docs/approval/approval-record.md`
- `docs/ai/ai-log.md`

## Scope and limits

Seven days, eight cities, exploratory screening only; weekend-only test after
weekday training. Results do not establish a causal weather effect or general
forecasting performance.