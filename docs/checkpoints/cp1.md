# Checkpoint 1: Data-mining lifecycle and data collection MVP

Tag: `cp1-mvp` (the full commit hash is recorded in
docs/checkpoints/evidence-register.md and in the final report)
Written approval: docs/approval/approval-record.md (email, 2026-10-28)
Issues: #1 collector MVP, #2 schema, #3 validation, #4 tests, #5 decisions

## Value statement
This component enables the university student support and campus safety office
to see current modelled PM2.5 and weather for eight Uzbek cities by collecting,
validating and storing Open-Meteo data on a schedule, resulting in a queryable
record per city and hour that carries its source, valid time, receipt time and
raw-response hash. Baseline for the manual route (V1-V3): to be measured before assessed
collection starts and recorded in a later checkpoint.

## Independent test specification
- Purpose: show that a new genuine record is collected, validated, stored with
  provenance and read back.
- Inputs: live Open-Meteo responses (collection) and fake responses in
  tests/fixtures/ (tests, no network).
- Expected outputs: eight cities `stored` (or `duplicate` for an hour already
  stored); `latest` lists rows with valid time, receipt time, PM2.5, wind speed,
  `native` and `pilot` flags.
- Commands (clean checkout, Windows):
  `pip install -r requirements.txt`, `python -m pytest -v`,
  `python -m uzair.cli collect`, `python -m uzair.cli latest`
- Acceptance criteria: (1) all tests pass; (2) `collect` stores a record per
  city with api_time_utc, collected_at_utc, endpoint, run_id and
  response_sha256; (3) `latest` returns the new record; (4) no key or account is
  needed; (5) development records carry `is_pilot=1`; (6) a wrong wind unit is
  quarantined, never stored as valid.
- Actual result (clean checkout, 2026-10-29, commit 41f54c7): 32 tests passed;
  `collect` stored 8 of 8 cities; `latest` returned 8 rows (`pilot=1`);
  `pip list` shows no unused HTTP library.

## Substantive change in this checkpoint
Schema and migrations, validation and quarantine, audited collector with retry,
CLI, hourly scheduler script, decisions 0001-0006.

## Known limits and next steps (CP2)
Stale-record check, location-echo check, large-jump flag, 10 s timeout,
coverage monitoring query, manual baselines V1-V3.

## AI assistance in this period
Claude and ChatGPT were used for planning, drafting and debugging; see
docs/ai/ai-log.md for what was checked, corrected or rejected.