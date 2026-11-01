# 0007 - Controls that protect assessed collection

Status: Accepted (2026-11-01)
Related: approval of 2026-10-28; issues #1, #3, #5

## Context
The approval allows assessed collection only from 2 November 2026, with a frozen collector,
scheduled polls only, and pilot/recovery records kept outside the main analysis. A forgotten
flag or a manual run could silently break these rules, and the UNIQUE(city, valid time)
constraint means a manual or development row would block the scheduled row of the same hour.

## Decision
- `collect --assessed` is refused (exit code 2, nothing written) unless all hold:
  inside 2026-11-01T19:00Z to 2026-11-08T19:00Z (= 2 Nov 00:00 to 9 Nov 00:00 Asia/Tashkent);
  `--scheduled` is also given; collector version has no `-dirty` or `+nogit` suffix.
  Implemented in `src/uzair/guards.py`, tested in `tests/test_guards.py`.
- Assessed runs write to their own database `data/assessed.db`; development runs use
  `data/uzair.db`. Development data therefore never share a table with assessed data.
- The development scheduled task is deleted before the window opens; a separate task
  `UzAir-assessed-collect` runs `scripts/run_collect_assessed.bat` at :05 every hour.
- No catch-up run: the task does not use "run as soon as possible after a missed start".
- `verify` recomputes the SHA-256 of every raw response; `provenance` shows the runs, HTTP
  status, latency, retries, hashes and collector version behind each row.

## Consequences
- A wrongly timed or manual assessed run cannot enter the data.
- The assessed database contains only assessed rows, so snapshot and analysis need no filtering
  (`is_pilot` is still stored and checked).
