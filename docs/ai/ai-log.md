# AI-use log

Tool: Claude (Anthropic), chat interface, used as development support.

| Date | Purpose | What was produced | How it was checked / changed / rejected |
|---|---|---|---|
| 2026-10-28 | Planning and repository setup guidance | Checkpoint plan, issue and decision-record drafts | confirmed API parameters against live responses |
| 2026-10-28 | Time-alignment decision (0002) | Draft decision record | Checked against real API samples (15-min weather vs hourly air-quality interval) |
| 2026-10-28 | SQLite schema, migration runner, schema tests | Draft SQL and Python | Ran `pytest`; files were first in the wrong folders (a `src` folder inside `migrations`), found with `dir /s /b`, moved `db.py` to `src\uzair\`; 9 tests passed |
| 2026-10-28 | Validation, collector, CLI, offline tests | validate.py, collector.py, query.py, cli.py, 16 tests | Ran on my machine; fixed 2 import/path errors (details below); live demo and database checks passed; commit 4572c05 |
| 2026-11-02 | Windows Task Scheduler setup | Used Claude's guidance to configure Windows Task Scheduler for automatic hourly execution of the UzAir data collector. | Followed the instructions, configured the scheduled task and checked its execution and collection logs. |

## 2026-10-28 — Validation, Collector and CLI

### Problem 1: Test imports failed

**Problem:** When I ran `python -m pytest -v`, two test modules failed with `ModuleNotFoundError: No module named 'conftest'`.

**My investigation:** I checked the test files and project structure. The issue was related to how helper modules were imported within the `tests` package.

**AI-assisted solution:** I used AI to understand the difference between top-level and relative imports in a Python package. I changed the imports to `from .conftest import ...` in both test modules.

**Verification:** I reran the test suite and confirmed that all 25 tests passed.

### Problem 2: The CLI could not find the Python package

**Problem:** Running `python -m uzair.cli collect` failed with `No module named 'uzair'`.

**My investigation:** I checked the project structure and found that `pytest.ini` configured `pythonpath = src`, but this setting did not apply to regular Python commands.

**AI-assisted solution:** I used AI to understand Python package installation and configured the project for editable installation using `pyproject.toml` and `pip install -e .`.

**Verification:** After installation, I checked that the CLI commands and test suite worked without manually setting `PYTHONPATH`.

### Reflection

I first investigated the errors by checking file locations, imports, and command behavior. I then used AI to understand the underlying Python packaging concepts and implement appropriate fixes. This helped me distinguish between pytest configuration and Python's package discovery mechanism.

### Hourly behavior check (2026-10-28, 15:05 Tashkent)

I assumed that hourly polling creates a new row each hour and that
`is_native_step` is 1 only on 3-hourly UTC boundaries. I tested this with
a second collect at 10:05Z: 8 of 8 cities were stored with valid=10:00Z
and native=0 (the earlier 09:00Z rows have native=1). The assumption was
confirmed. Native-only analysis will have at most 56 rows per city over
7 days.

## ChatGPT assistance

Tool: ChatGPT (OpenAI), chat interface.

| Date | Purpose | Assistance provided | Verification and my contribution |
|---|---|---|---|
| 2026-11-03 | Module Leader clarification and analysis protocol | Helped interpret the Module Leader's email on native three-hourly analysis, hourly sensitivity analysis, exact t+6 h matching and sample-size reporting. Helped translate these requirements into documentation changes for the analysis protocol. | The Module Leader's written email was treated as the authoritative requirement. I reviewed and applied the documentation changes. |
| 2026-11-04 | CP1 documentation and evidence review | Helped review the CP1 checkpoint addendum, evidence register, decision record and manual baseline. Helped identify documentation inconsistencies and clarify the manual baseline transcription result. | Repository files, Git history and command outputs were checked. I confirmed that the manual baseline contained 9 correct entries and 1 incorrect entry out of 10. |

ChatGPT suggestions were treated as assistance rather than evidence. Final documentation claims were checked against repository files, Git history, command outputs and the Module Leader's written instructions. Unverified results were not reported as completed.

### 2026-11-10: CP2 evidence review and documentation

Tool: ChatGPT (OpenAI), chat interface.

Purpose: Review the Checkpoint 2 evidence and documentation against the actual repository state, command outputs and the Module Leader's late-freeze instructions.

Assistance provided:
- Reviewed the CP2 checkpoint draft, coverage and audit evidence, incident records and AI-use log.
- Helped distinguish observed coverage figures from earlier estimates: 1,311 valid primary rows, 302/336 hourly test pairs and 88/112 native three-hourly test pairs.
- Helped document the 6 November partial poll, the 8 November DNS failures and the two missed polls with UTC and Asia/Tashkent times.
- Identified that the available Task Scheduler evidence did not establish the cause of the two missed polls; the cause was therefore recorded as unknown.
- Advised not to run preparation or snapshot commands before the late-freeze decision and required checks were documented.

My verification and contribution:
I ran the commands in the development repository and supplied their outputs. I reviewed and corrected the incident and checkpoint documentation. The test suite returned 82 passed, and the assessed database verification reported 2,638 raw responses checked with 0 hash mismatches. ChatGPT did not independently run these commands or inspect the live database.

### 2026-11-11: Stakeholder queries and tests

Tool: Claude (Anthropic), AI assistant.

Purpose: Assist with drafting the read-only stakeholder queries and their tests for the CP2 monitoring work.

Assistance provided:
- Helped draft `monitoring/queries.py` and `tests/test_queries.py`.
- The initial suggestions did not fully match the project's actual database structure and requirements.

My review and contribution:
I reviewed and substantially edited both files because several parts of the initial suggestions did not match the project's actual database structure and requirements. I checked the final implementation against the repository and the intended stakeholder-query requirements. I treated Claude's initial suggestions as drafts, not as verified evidence.
