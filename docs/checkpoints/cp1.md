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
- Actual result (clean checkout, 2026-11-01, commit
  07265222564e7d64ab45788b55f79cc5c9cec314): 54 tests passed;
  `collect` stored 8 of 8 cities; `latest` returned 8 rows
  (`pilot=1`); `provenance -n 2` returned provenance details;
  `verify` checked 16 raw responses with 0 hash mismatches;
  `status` reported 8 pilot observations and 16 successful pilot runs.
  The assessed scheduled collection guard correctly refused collection
  before its configured opening time (`2026-11-01T19:00:00Z`).
  Demo output: `docs/checkpoints/cp1-demo-output.txt`.
  Code was tested at commit
  `07265222564e7d64ab45788b55f79cc5c9cec314`;
  the following commit (`3ca83b0`) only records this verification result.

  
## Substantive change in this checkpoint
Schema and migrations, validation and quarantine, audited collector with retry,
CLI, hourly scheduler script, decisions 0001-0006.

## Known limits and next steps (CP2)
Stale-record check, location-echo check, large-jump flag, 10 s timeout,
coverage monitoring query, manual baselines V1-V3.

## AI assistance in this period
Claude and ChatGPT were used for planning, drafting and debugging; see
docs/ai/ai-log.md for what was checked, corrected or rejected.

## Addendum 2026-11-04 (written after the CP1 commit; the text above is unchanged)
- Tag: the checkpoint tag is `cp1-submission` (commit 0726522, code tested and then frozen for
  collection). The earlier tag `cp1-mvp` marks an intermediate commit (cd6e964) and is kept.
  Commit f91e034 contains the same code plus the recorded clean-checkout result.
- Items listed above as open were done before assessed collection started: the manual baseline
  V1-V3 (docs/baseline/manual-baseline.md, commit 0726522) and the 10 s timeout (commit 2941822).
- Commit a6a774e bundled several changes in one commit without issue references
  (assessed-collection guard, provenance and verify commands, protocol, baseline
  template, scheduler scripts). The assessed-collection controls are documented
  in decision 0007. The combined implementation is identifiable in commit
  a6a774e; later commits are kept small and reference issues where applicable.
- Assessed collection started on 2026-11-02 00:05 (Asia/Tashkent). It is CP2 evidence, not CP1.
