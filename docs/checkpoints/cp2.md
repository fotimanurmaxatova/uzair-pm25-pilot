# Checkpoint 2: Reliable collection and data quality

Tag: `cp2-submission` | Full commit hash: recorded in `docs/checkpoints/evidence-register.md` in a commit made after the tag (the hash of a commit cannot be written inside that commit)
Issues: #9 coverage report, #10 quality audit, #11 analysis-ready table, #12 data snapshot, #13 incident records and decision 0008, #14 stakeholder queries (acceptance criteria in each issue) | Decisions: 0007, 0008, 0009 | Incidents: 2026-11-02-weather-503, 2026-11-06-partial-poll, 2026-11-08-missed-polls

## Value statement
This component enables the university student support and campus safety office to judge whether the week's air-quality collection is reliable enough to trust by running database-preserving audit and monitoring reports and stakeholder queries, with the preparation tool writing only a separate derived output file, resulting in a reproducible set of reports and queries that show 1,311 valid rows against the 1,344 maximum (97.5%; target 1,000), every failed, partial or missed poll with its recorded reason or explicitly unknown cause, the longest gap per city, the usable exact t -> t+6 h test-partition pairs for native 3-hourly primary data and hourly sensitivity data, and an audit of stale rows, location echo, jumps and grid-cell sharing.

## What this checkpoint covers (brief: reliable collection, data quality, queries, growing real data)
| Requirement | Evidence |
|---|---|
| Continued genuine acquisition | Assessed window 2-8 Nov 2026, 168 scheduled polls from the frozen collector (`0726522`, tag `cp1-submission`); 2,656 requests, 1,311 valid rows (target 1,000) |
| Schema and data validation | `migrations/`, `src/uzair/validate.py`, boundary tests for every limit (issues #2, #3); 0 quarantined rows in the live data, quarantine behaviour covered by tests |
| Duplicate and error handling | `UNIQUE(city_id, observation_hour_utc)` (`test_duplicate_city_hour_is_blocked`); retry with backoff, failed runs recorded with reasons (`test_timeout_retries_then_fails_and_is_audited`, `test_http_500_is_retried_then_recorded_as_failed`, `test_4xx_is_not_retried`) |
| Audit and provenance fields | `collection_runs`, `raw_responses` (SHA-256), `collector_versions`; `python -m uzair.cli --db <db> verify` re-hashes every raw response |
| Cleaning | `monitoring/prepare.py` (issue #11): original values never changed, exact valid-time matching, missing stays missing, prints counts only |
| Stakeholder queries and monitoring output | `monitoring/queries.py` (6 queries, issue #14), `monitoring/coverage.py` (#9), `monitoring/audit.py` (#10); outputs in `docs/coverage/` |
| Reproducible data | `snapshots/` with `MANIFEST.json` (SHA-256 of every file), attribution, collection log (issue #12) |
| Evidence of progress toward the target | 1,311 of 1,344 possible rows (97.5%) against the approved minimum of 1,000 |

## Independent test specification
- Purpose: show that collection continued genuinely, failures are visible, quality is audited and the analysis-ready table is reproducible.
- Inputs: `snapshots/assessed_snapshot.db` (SQLite copy of the live collection, 2-8 Nov); synthetic rows in `tests/` (tests only, never analysed).
- Commands (clean checkout): create a virtual environment with `python -m venv .venv`, install dependencies with `.venv\Scripts\python.exe -m pip install -r requirements.txt`, run `.venv\Scripts\python.exe -m pytest -q`, then set the database path with `set "DB=snapshots\assessed_snapshot.db"` and run:
  `.venv\Scripts\python.exe -m uzair.cli --db %DB% verify`, `.venv\Scripts\python.exe -m monitoring.coverage --db %DB%`, `.venv\Scripts\python.exe -m monitoring.audit --db %DB%`,
  `.venv\Scripts\python.exe -m monitoring.queries --db %DB%`, `.venv\Scripts\python.exe -m monitoring.prepare --db %DB% --out derived\analysis_rows.csv`.
- Expected: tests pass; verify finds 0 mismatches; coverage prints sections 1-5; audit prints sections 1-5; queries print six sections; prepare prints counts only.
- Acceptance criteria: (1) all tests pass; (2) verify, coverage, audit and stakeholder-query commands do not mutate the source database; `prepare` writes only the derived output file, and snapshot creation writes a separate snapshot; (3) the approved maxima reproduce (336 hourly and 112 native test pairs); (4) failed, missed and partial polls are distinguished; (5) collection and receipt timestamps are preserved for the CP3 strict fitting cut-off; (6) pilot rows are never counted; (7) lags and the target are matched by exact valid time; (8) a tampered raw response causes snapshot verification to fail.
- Actual result (assessed collection and canonical snapshot; checks run on 2026-11-10 and 2026-11-11): 93 tests passed; `verify`: 2,638 raw responses re-hashed, 0 hash mismatches; coverage: 1,311 of 1,344 valid rows (97.5%), polls complete 163, partial 1, failed 2, missed 2; usable test-partition pairs 88 of 112 (native 3-hourly, primary) and 302 of 336 (hourly, sensitivity analysis); audit: 1,311 rows audited, 0 pilot rows, 0 stale receipts, 0 jumps above 100 ug/m3, 0 quality flags, 0 location mismatches, 0 shared grid cells; queries: 26 failed requests, 8 requests succeeded after retry, 0 quarantined. A clean-checkout run and its captured output will be added in step 3 before the checkpoint is committed.

## Substantive change since Checkpoint 1
Assessed collection ran 2-8 Nov from the frozen CP1 code. New in the repository since tag `cp1-submission`: `monitoring/` (coverage, audit, prepare, snapshot, queries) with tests, the data snapshot and manifest, decisions 0008 and 0009, three incident records, coverage, audit and query reports, the native-primary clarification in the analysis protocol (#6), boundary tests for temperature, pressure and wind direction (#3). Run `git diff --stat cp1-submission..cp2-submission` for the full list.

## Failures and corrections (traceability evidence)
- 2 Nov 20:05 Asia/Tashkent: weather HTTP 503 in all cities, retried, one poll lost, no back-fill (incident record).
- 6 Nov 22:05: one city partial (weather timeout, air-quality DNS error), gap kept (incident record).
- 8 Nov 17:05 and 18:05: two polls missed, cause unknown (Task Scheduler operational log was disabled, so sleep is not claimed); 8 Nov 20:05: DNS errors in all cities (incident record).
- 8 successful requests needed one or three retries (`retries.py` output); the slowest successful request took 14,110 ms with no retry (the 10 s timeout is per socket operation, not per request; cause not established).
- Stale, location, jump and grid-cell checks cannot be added to the frozen collector; they run as post-hoc audits.
- Corrections: decision 0008 status date corrected to the date it was written (2026-11-11, commit 8a86954); the first draft's estimate of test pairs (about 96 and 312) was replaced by the reported 88 and 302; the draft's unproven "laptop asleep" cause was removed.

## Known limits / next step (CP3)
Late model freeze (decision 0009): selection script with receipt-time cut-offs that fails if a test-origin row is loaded, selected configurations committed and tagged as a late freeze, then one test evaluation. Missing weather/NO2 values after lag construction are counted in CP3. The `pressure_change_3h` column has 49 missing values (no row exactly three hours earlier); they are not filled.

## AI assistance in this period
See `docs/ai/ai-log.md`. Claude (Anthropic) drafted code, tests and text that I reviewed and ran on my machine: the `monitoring/` tools and their tests (first pack, 2026-11-08 to 2026-11-10), the boundary tests (2026-11-10), `monitoring/queries.py` and its tests (2026-11-11), drafts of decisions 0008 and 0009 and of the issue texts. I ran every command myself and pasted the real outputs; facts in the incident records come from my own `incidents.py`, `retries.py`, Event Viewer and coverage outputs. Other tools I used are listed in the AI log.
