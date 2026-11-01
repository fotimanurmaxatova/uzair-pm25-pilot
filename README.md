# uzair-pm25-pilot

UzAir: Predicting Modelled PM2.5 from Weather in Uzbek Cities (UDE5014CM CW2)

A seven-day exploratory pilot (approved 2026-10-28, assessed collection from
2 November 2026). It collects weather (Open-Meteo forecast API) and modelled
PM2.5 and related pollutants (Open-Meteo air-quality API, CAMS global domain)
for eight Uzbek cities into a local SQLite database, with validation,
provenance and an audit trail. The target is the API's later modelled PM2.5
estimate, not a measured concentration or a health-safety judgement.

## Status

Checkpoint 1 (MVP): collection path with validation, provenance, SQLite
storage and read-back, hourly scheduler, automated tests.
Planned: monitoring queries, analysis (Q1 to Q5), dashboard/API, report.

## Requirements

Python 3.10 or newer (developed on 3.12, Windows). Internet access for live
collection; the tests use fake responses and need no network.

## Clean install (Windows)

```
git clone https://github.com/fotimanurmaxatova/uzair-pm25-pilot.git
cd uzair-pm25-pilot
python -m venv .venv
.venv\Scripts\activate
pip install -e .
pip install pytest
pip install -r requirements.txt
```

## Run the tests

```
python -m pytest -v
```

Expected: all tests pass (54 at the time of writing).

## Collect and read back

```
python -m uzair.cli collect
python -m uzair.cli latest
python -m uzair.cli latest -n 16
python -m uzair.cli provenance -n 2   # runs, HTTP status, latency, retries, hashes, collector version
python -m uzair.cli verify            # recompute SHA-256 of every stored raw response
python -m uzair.cli status            # row and run counts by pilot flag
```

- `collect` polls all eight cities once (weather + air quality). The database
  `data/uzair.db` is created automatically from `migrations/`.
- By default rows are development data (`is_pilot=1`). Assessed collection
  needs the explicit flag `--assessed` (`is_pilot=0`).
- `--scheduled` marks the run as scheduled (`acquisition_mode='scheduled'`);
  without it the run is `manual`.
- `--db data/dev.db` keeps a run in a separate database file. `--assessed` writes to
  `data/assessed.db` by default, so assessed and development data never share a database.
- `--assessed` is refused (exit code 2, nothing written) outside 2 Nov 00:00 to 9 Nov 00:00
  Asia/Tashkent, without `--scheduled`, or when `src/` or `migrations/` have uncommitted
  changes (decision 0007).

## Scheduled collection (Windows Task Scheduler)

Development (rows flagged `is_pilot=1`, database `data/uzair.db`):

```
schtasks /create /tn "UzAir-dev-collect" /tr "<repo path>\scripts\run_collect.bat" /sc hourly /mo 1 /st 00:05 /f
```

Assessed (2 Nov 00:05 to 8 Nov 23:05, 168 hourly runs, database `data/assessed.db`):
delete the development task first, then run
`powershell -ExecutionPolicy Bypass -File scripts\register_assessed_task.ps1`.
The task runs `scripts/run_collect_assessed.bat` and appends to `logs/assessed.log`.
The computer must stay on, awake and set to Tashkent time; missed hours remain gaps
(no catch-up run, no back-filling).

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

## Data sources and attribution

- Weather and air-quality data:
  [Weather data by Open-Meteo.com](https://open-meteo.com/), licensed
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The data snapshot
  stored in this repository is redistributed under the same licence. Raw values
  are stored unchanged; derived values are labelled as derived.
- Weather: Open-Meteo Forecast API with `models=best_match`. The underlying
  weather model may depend on location; see the
  [Open-Meteo documentation](https://open-meteo.com/en/docs).
- Air quality: Open-Meteo Air Quality API with the `cams_global` domain. The
  underlying forecasts come from the Copernicus Atmosphere Monitoring Service
  (CAMS global atmospheric composition forecasts); see the
  [Open-Meteo Air Quality API documentation](https://open-meteo.com/en/docs/air-quality-api).
- Request volume: about 384 requests per day (8 cities x 2 endpoints x 24
  runs), at most 1,536 per day with maximum retries, below the free-API limits
  (see `docs/decisions/0006-data-licence-and-rate-limits.md`). This assumes the
  scheduler is configured and running.
- Pending: the exact CAMS attribution wording for the dashboard and report is
  verified before CP4 (tracked in decision 0006).
- City coordinates: reference table, see
  `docs/decisions/0005-city-coordinates.md`.

## Project structure

```
src/uzair/        collector, validation, database, queries, CLI
migrations/       SQL schema and city seed (applied in order)
scripts/          scheduler script
tests/            automated tests; tests/fixtures/ holds fake API responses
docs/decisions/   decision records
docs/approval/    written approval record
docs/protocol/    analysis protocol fixed before assessed collection (class hours, features, rules)
docs/baseline/    manual baseline for value measures V1 to V3
docs/checkpoints/ checkpoint specifications and evidence register
docs/ai/          AI-use log
data/, logs/      databases and logs (not committed)
```

## Documentation

- `docs/decisions/` (API parameters, time alignment, weather model, city
  coordinates, data licence and rate limits)
- `docs/approval/approval-record.md`
- `docs/ai/ai-log.md`

## Scope and limits

Seven days, eight cities, exploratory screening only; weekend-only test after
weekday training. Results do not establish a causal weather effect or general
forecasting performance.

