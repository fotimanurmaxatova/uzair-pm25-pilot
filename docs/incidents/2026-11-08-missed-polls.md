# Incident 2026-11-08: two scheduled polls were missed

## What happened

The assessed collection window contained 168 scheduled hourly polls (2-8 November 2026, Asia/Tashkent).

The coverage report classifies 166 polls as started: 163 complete, 1 partial and 2 failed. Two scheduled polls, at 17:05 Asia/Tashkent (12:05 UTC) and 18:05 Asia/Tashkent (13:05 UTC) on 8 November, were recorded as missed.

Two additional incidents are relevant to the assessed collection:

- **6 November 2026, 17:05:02-17:06:11 UTC (22:05:02-22:06:11 Asia/Tashkent): partial poll.** Tashkent weather retrieval timed out at 17:05:02 UTC (22:05:02 Asia/Tashkent). Tashkent air-quality retrieval failed with a DNS resolution error at 17:06:11 UTC (22:06:11 Asia/Tashkent). The poll returned data for 7 of the 8 cities.
- **8 November 2026, 15:05-15:08 UTC (20:05-20:08 Asia/Tashkent): failed poll.** Weather and air-quality requests encountered DNS resolution errors across all eight cities. These failures are recorded in the assessed database and reported by `python C:\UzAir_tools\incidents.py`.

## Cause of the missed polls

The cause of the two missed polls on 8 November is unknown.

The Task Scheduler Operational event log is currently disabled (`enabled: false`), and the available evidence does not establish that the laptop was asleep at the missed times. No confirmed sleep interval or other root cause has been identified.

## Handling

- The two missed hours remain gaps in the assessed dataset.
- The missed polls are included in the coverage report and are not hidden from the totals.
- No claim is made that the missed polls were caused by laptop sleep.
- The 6 November partial poll and 8 November DNS failures are recorded separately from the missed polls.
- No recovery download or back-fill was used to fill these gaps.

## Impact

According to the coverage report:

- Valid primary rows: 1,311 of 1,344 (97.5%).
- The minimum target of 1,000 valid rows was met.
- Test partition usable pairs: 302/336 hourly and 88/112 native three-hourly.

These are the actual reported counts; they should not be replaced with earlier estimates.

## Improvements for a longer study

- Enable and retain Task Scheduler Operational logging.
- Use an always-on collection host where possible.
- Check power and sleep settings before each collection period.
- Add a heartbeat alert when a scheduled poll is missed.
