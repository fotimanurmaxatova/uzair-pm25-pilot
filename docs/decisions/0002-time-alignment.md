2. Decision record 0002

Yangi fayl: docs/decisions/0002-time-alignment.md

markdown
# 0002 — Time alignment of weather and air-quality records

Status: Accepted (2026-10-28)
Related: Issue #1, #3, #5; builds on decision 0001

## Context
Live sample responses (Tashkent, saved as test fixtures) show:
- Weather `current`: interval 900 s (15 min); valid time is not on the hour.
- Air quality `current` (domains=cams_global): interval 3600 s, valid time on the hour.
- The air-quality source is natively three-hourly (CAMS global, ~0.4°), so an
  hourly output step does not mean independent hourly measurements.
- Weather and air-quality grids differ slightly (about 0.01° offset in the sample).

## Decision
- One observation row = one city + one air-quality valid time.
  `observation_hour_utc` = the air-quality valid time (UTC, on the hour).
- The weather valid time is stored separately (`weather_time_utc`).
  A record is accepted only if the weather valid time is within 3600 s of the
  air-quality valid time; otherwise it is quarantined (`time_mismatch`).
- The collector also stores `aq_interval_s`, `weather_interval_s`, `aq_domain`
  and `is_native_step` (observation hour UTC divisible by 3). The native-step
  alignment is an assumption to verify on the first days of real data.
- UNIQUE(city_id, observation_hour_utc): repeated polls returning an
  already-stored air-quality valid time are counted as duplicates.
- Outcome matching uses `observation_hour_utc + 6 h` for the same city (exact
  valid time, never row position).
- PM2.5 > PM10 is quarantined as `pm_inconsistent`; PM2.5 == PM10 is allowed
  (the sample shows a ratio of 0.97, so equality is a realistic boundary case).

## Consequences
- Rule A sensitivity analysis restricted to native-step times is feasible.
- A dedicated boundary test covers PM2.5 == PM10.
- Weather values are 15-minute "current" values, not hourly means; this is a
  documented validity limit.
