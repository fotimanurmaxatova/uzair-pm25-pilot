# 0008 - Operating the assessed collection: frozen code, backups, coverage reporting

Status: Accepted 2026-11-11 (written after the collection window; follows the Module Leader's reliability reply of 2026-10-28)
Related: 0003, 0005 (as the Module Leader requested), 0007; incidents 2026-11-02-weather-503, 2026-11-06-partial-poll and 2026-11-08-missed-polls; issue #5

## Context

The Module Leader's reply on reliability accepted collection on my laptop, allowed a separate recovery table that never enters the primary analysis, and asked for: no overlapping runs, backups, a restart/logout test, failure monitoring, and coverage reported as valid rows, run outcomes, coverage by city/day/partition, longest gaps and usable exact t -> t+6 h pairs.

## Facts (checked on 2026-11-10)

- **Collector code freeze:** the assessed collector ran from commit `0726522` (tag `cp1-submission`) in the separate collection folder (`C:\UzAir_collect`). The assessed database records collector version `0.1.0+0726522` across all 2,656 collection runs. The development-repository comparison `git diff --stat 0726522 HEAD -- src migrations` showed one change: `src/uzair/query.py` (6 insertions, 2 deletions). This adds weather and air-quality endpoint fields to the provenance query; it does not change the assessed collector's collection process. The collection folder was kept separate from development work.

- **Outcome:** 166 of 168 scheduled polls ran; 1,311 valid primary rows of 1,344 (97.5%); 2,656 runs (2,630 successful, 26 failed); 0 quarantined rows; 2,638 raw responses were re-hashed with 0 mismatches.

- **Raw responses:** 1,311 weather responses, 1,319 air-quality responses (including the 8 air-quality responses from the 2 November 20:05 poll, when weather requests failed), and 8 failed weather responses retained as raw evidence.

- **Overlap prevention:** the scheduled task used `-MultipleInstances IgnoreNew`; no catch-up run was configured (`register_assessed_task.ps1`).

- **Backups:** three copies are kept in `C:\UzAir_backup` (`assessed.db`, `assessed_2026-11-08.db`, `assessed_final.db`). Checked on 2026-11-11, each contains 1,311 observations (first `2026-11-01T19:05:04Z`, last `2026-11-08T18:05:33Z`) and 2,656 runs (last start `2026-11-08T18:05:29Z`), the same as the live database. The live database and `assessed.db` have SHA-256 `d078c74161aeaba5dfda474070dfae71d7de4df58aacce6673b44e0ae8091256`. The two copies have the same SHA-256 as `assessed_snapshot.db`, created by `monitoring.snapshot` on 2026-11-11 using SQLite's online-backup mechanism. They are therefore byte-for-byte identical to that snapshot. The live database and `assessed.db` have a different SHA-256, although their observation and run counts and time range match. The original method used to create the two backup copies was not recorded. The data snapshot is taken from the live database.

- **Scheduled task:** `\UzAir-assessed-collect` is currently `Disabled`. Its last run was 8 November 2026 at 23:05:01 (Asia/Tashkent), with result `0`. The exact time when the task was disabled is not established. The task registration script is retained in `C:\UzAir_collect\scripts\register_assessed_task.ps1`.

- **Restart evidence:** Windows System logs record a restart on 3 November 2026 at approximately 19:37 (Asia/Tashkent). The assessed collection log records the next hourly poll at 20:05:01, which completed with `exit=0`. This demonstrates that collection resumed after that restart. A separate Windows logout test was not confirmed.

- **Recovery download:** no recovery download or back-fill was used to fill missed poll times. The assessed database contains no separate recovery table. Its tables are `cities`, `collection_runs`, `collector_versions`, `observations`, `quarantine`, `raw_responses`, and `schema_migrations`.

## Decisions

1. New work is developed in a separate clone; the collection folder was not edited or pulled.
2. Coverage and eligibility are reported with the read-only `monitoring/coverage.py`; quality is audited after collection with `monitoring/audit.py` (stale, location echo, jumps, grid cells, series similarity), because the frozen collector does not apply those checks. Nothing is deleted or relabelled.
3. Analysis-ready data come from `monitoring/prepare.py`, which never changes original values.
4. The final data snapshot is created with `monitoring/snapshot.py` after the late freeze (see `docs/decisions/0009` once written).

## Consequences

Collection evidence stays clean and reporting follows the Module Leader's list.
