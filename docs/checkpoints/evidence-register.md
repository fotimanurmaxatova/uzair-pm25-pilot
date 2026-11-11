# Checkpoint evidence register

Full 40-character hashes of the commits submitted for each checkpoint. A commit cannot contain its own
hash, so each hash is recorded in a later commit and in the final report. The Module Leader confirmed
(email of 2026-10-28) that no separate checkpoint form is required and that hashes and evidence
records go with the final report.

| Checkpoint | Tag | Deadline (LMS) | Full commit hash | Operational component and substantive change | Tests and verifiable results |
|---|---|---|---|---|---|
| 1 Data-mining lifecycle and collection MVP | `cp1-submission` (code frozen, commit 0726522) | No deadline listed in LMS | `f91e034e81d8637cfd6f28308cbd86a3c99e17e5` (evidence record); code identical to `07265222564e7d64ab45788b55f79cc5c9cec314` (tag `cp1-submission`, the commit the assessed collector runs from) | Audited Open-Meteo collector, SQLite schema and migrations, validation and quarantine, provenance, assessed-collection guard, provenance and verify commands, manual baseline V1-V3 | docs/checkpoints/cp1.md, docs/checkpoints/cp1-demo-output.txt (54 tests passed, 8 of 8 cities stored, 0 hash mismatches) |
| 2 Reliable collection and data quality | `cp2-submission` | No deadline listed in LMS | `af3373939ac7961c979319ad87dc2903e31bf0b7` | Reliable collection monitoring, coverage and audit reports, stakeholder queries, snapshot verification and derived-output preparation | `docs/checkpoints/cp2.md` (93 tests passed; 2,638 raw responses verified, 0 hash mismatches; 97.5% coverage; native 3-hourly 88/112 and hourly sensitivity 302/336 usable pairs) |
| 3 Statistical analysis and decision support | | | | | |
| 4 Integrated data-producing system | | | | | |
