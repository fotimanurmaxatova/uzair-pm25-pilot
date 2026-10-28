# 0001 — API parameters, units and timestamps

Status: Accepted (2026-10-28)
Related: Issue #1, #5; approval email from Module Leader (see docs/approval/)

## Context
Open-Meteo returns wind speed in km/h by default, but the project's thresholds
and regression coefficients are defined in m/s. Time fields must also be
unambiguous so that outcomes can be matched to the exact valid time.
The global air-quality source has three-hourly native resolution.

## Decision
Weather endpoint (https://api.open-meteo.com/v1/forecast):
- `wind_speed_unit=ms` is always set explicitly; the collector rejects any
  response whose returned wind unit is not "m/s".
- `timeformat=unixtime` and `timezone=GMT`; times are stored in UTC.

Air-quality endpoint (https://air-quality-api.open-meteo.com/v1/air-quality):
- The model domain is set explicitly (`domains=cams_global`) and recorded
  with each response. Exact parameter names are confirmed against the live
  documentation before CP1 is frozen.

For every source the collector stores: valid timestamp, returned units, and
model/domain.

## Valid time vs receipt time
- `api_time_utc` = valid time (the time the value refers to).
- `collected_at_utc` = receipt time (when our collector received it).
- Original collected values are never modified. Outcome matching uses valid
  time (same city, t + 6 h); training eligibility uses receipt time.

## Consequences
- Hourly polling of a three-hourly source does not give independent hourly
  measurements; a sensitivity analysis uses native-step times only.
- Missed polls remain gaps; recovery records go to a separate table and are
  not used in the primary analysis.
