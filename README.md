# uzair-pm25-pilot

UzAir: Predicting Modelled PM2.5 from Weather in Uzbek Cities (UDE5014CM CW2)

A seven-day exploratory pilot (approved 2026-10-28, assessed collection from
2 November 2026). It collects weather (Open-Meteo forecast API) and modelled
PM2.5 and related pollutants (Open-Meteo air-quality API, CAMS global domain)
for eight Uzbek cities into a local SQLite database, with validation,
provenance and an audit trail. The target is the API's later modelled PM2.5
estimate, not a measured concentration or a health-safety judgement.

## Status

Implemented: data collection, validation, provenance, SQLite storage,
hourly scheduling, automated tests, coverage reporting, post-collection
quality audits, stakeholder queries and reproducible assessed snapshots.

Next: late model freeze under decision 0009, analysis (Q1 to Q5), dashboard/API and final report.

## Requirements

Python 3.10 or newer (developed on 3.12, Windows). Internet access for live
collection; the tests use fake responses and need no network.

## Clean install (Windows)

```cmd
git clone https://github.com/fotimanurmaxatova/uzair-pm25-pilot.git
cd uzair-pm25-pilot
python -m venv .venv
.venv\Scripts\activate
pip install -e .
pip install pytest
pip install -r requirements.txt
```

## Run the tests

```cmd
python -m pytest -v
```

Expected: all tests pass. The test suite is maintained as the project evolves.

## Collect and read back

```cmd
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

```cmd
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
  3-hourly UTC boundaries. Native three-hourly rows are the primary analysis;
  all eligible hourly rows are a labelled sensitivity analysis (see
  `docs/protocol/analysis-protocol.md`).

## Monitoring and data quality

The monitoring tools provide read-only reports against the assessed SQLite
snapshot. They do not modify the source database.

Run coverage and forecast-eligibility reporting:

```cmd
python -m monitoring.coverage --db snapshots\assessed_snapshot.db
```

Verify raw-response hashes inside the snapshot:

```cmd
python -m uzair.cli --db snapshots\assessed_snapshot.db verify
```

Run the post-collection quality audit:

```cmd
python -m monitoring.audit --db snapshots\assessed_snapshot.db
```

Run all six stakeholder queries (daily coverage, hourly completeness,
request outcomes, quarantine, API latency and failures):

```cmd
python -m monitoring.queries --db snapshots\assessed_snapshot.db
```

Run one stakeholder query, for example request outcomes:

```cmd
python -m monitoring.queries --db snapshots\assessed_snapshot.db --query outcomes
```

Prepare analysis-ready rows:

```cmd
python -m monitoring.prepare --db snapshots\assessed_snapshot.db --out derived\analysis_rows.csv
```

This preparation step writes a derived CSV file; it does not modify the
assessed database. The resulting file is an input to the subsequent analysis
stage.

The CSV contains every valid assessed row, including the test period. Only
counts are printed on screen, and under decision 0009 the file is not opened
or analysed before the late model freeze.

### Assessed snapshot

The versioned `snapshots/` directory contains:

- `assessed_snapshot.db` — SQLite online-backup copy of the assessed database,
  including raw response bodies.
- `MANIFEST.json` — creation time, source database name, row counts,
  raw-response hash-check result and SHA-256 hashes of the snapshot files.
- `ATTRIBUTION.md` — attribution statement for the redistributed data.
- `cities.csv`, `collector_versions.csv`, `collection_runs.csv`,
  `observations.csv` and `quarantine.csv` — CSV exports of the corresponding
  database tables.
- `collection_log.txt` — copy of the assessed collection log.

Raw response bodies are retained inside the SQLite database and are not
exported into a separate CSV file. The snapshot creation process verifies
all stored raw-response hashes before writing the snapshot.

To create or refresh a snapshot from the original assessed database
(maintainer operation; requires access to the collection machine's files):

```cmd
python -m monitoring.snapshot --db C:\UzAir_collect\data\assessed.db --log C:\UzAir_collect\logs\assessed.log --out snapshots
```

The snapshot is redistributed under CC BY 4.0. See
[Data sources and attribution](#data-sources-and-attribution) and
`snapshots/ATTRIBUTION.md` for attribution details.

### Assessed snapshot quality summary

Coverage report generated on 11 November 2026:

- 1,311 valid primary rows out of 1,344 possible (97.5%).
- 163 complete polls, 1 partial poll, 2 failed polls and 2 missed polls.
- 302/336 usable hourly test pairs and 88/112 native 3-hourly test pairs.

Post-collection audit:

- No stale rows, large hourly PM2.5 jumps or location-echo mismatches.
- No shared grid cells between cities for either endpoint.
- No city pair met the 50% identical-value similarity threshold.

These are results for the versioned assessed snapshot, not guarantees
about future collections. API latency measures the final HTTP attempt;
it excludes earlier retries and backoff delays.

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

```text
src/uzair/        collector, validation, database, queries, CLI
migrations/       SQL schema and city seed (applied in order)
scripts/          scheduler script
tests/            automated tests; tests/fixtures/ holds fake API responses
docs/decisions/   decision records
docs/approval/    written approval record
docs/protocol/    analysis protocol fixed before assessed collection (class hours, features, rules)
docs/baseline/    manual baseline for value measures V1 to V3
docs/checkpoints/ checkpoint specifications and evidence register
docs/incidents/   incident records for the assessed collection
docs/coverage/    coverage, audit and query reports
docs/ai/          AI-use log
data/, logs/      databases and logs (not committed)
monitoring/       coverage, audit, stakeholder queries, preparation, snapshot
snapshots/        assessed SQLite snapshot, CSV exports, manifest and attribution
derived/          generated analysis-ready data (not committed)
```

## Documentation

- `docs/decisions/` (API parameters, time alignment, weather model, city
  coordinates, data licence and rate limits, assessed-collection controls,
  operating the assessed collection, late model freeze)
- `docs/approval/approval-record.md`
- `docs/incidents/`
- `docs/coverage/`
- `docs/protocol/analysis-protocol.md`
- `docs/ai/ai-log.md`

## Scope and limits

Seven days, eight cities, exploratory screening only; weekend-only test after
weekday training. Results do not establish a causal weather effect or general
forecasting performance.
