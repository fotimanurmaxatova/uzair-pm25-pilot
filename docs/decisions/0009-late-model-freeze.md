# 0009 - Late model freeze and retrospective held-out evaluation

Status: Accepted 2026-11-11 (written after the Module Leader's written approval of 2026-11-10)
Related: #8; decision 0007 (collector freeze); analysis protocol (`docs/protocol/analysis-protocol.md`)

## Context

The analysis protocol required the model, hyperparameters and preprocessing to be frozen and tagged by Friday 6 November 2026, 23:30 (Asia/Tashkent), with the final fit cut-off at 22:00 (= 17:00 UTC). I did not complete the cross-validation selection, and I did not commit or tag a frozen configuration by then. I was still working on the assessed-collection monitoring, data-quality checks and supporting documentation, and no model configuration was ready to be frozen.

No frozen model configuration existed in the repository when this record was written. The collector and schema were frozen at commit `0726522` (tag `cp1-submission`) and were not changed during the assessed window. The collector freeze is a different event from the model freeze described here and is not affected by it.

I reported the deviation to the Module Leader by email on 8 November 2026, before any test evaluation. The Module Leader approved the handling below on 10 November 2026 as a documented amendment for retrospective evaluation, subject to five conditions. This record implements those conditions.

## What had and had not been looked at (audit statement)

- No model has been fitted on the assessed data.
- No test-origin outcome (7 Nov 00:00 to 8 Nov 17:00 Asia/Tashkent) has been examined at individual-origin level, plotted, or summarised for model evaluation or selection.
- Read-only monitoring scripts (`check_assessed.py`, `monitoring.coverage`, `monitoring.audit`) printed aggregate counts, flag totals and overall ranges over the whole database, including the test period. They produced no per-origin outcome analysis, plots or model error summaries. This aggregate access is disclosed here; the test period is not described as wholly untouched.
- The raw-response hash check (`verify`) and the backup comparison checked integrity and file hashes only.
- `monitoring.prepare` and `monitoring.snapshot` had not been run when this record was written. The analysis-ready CSV has not been opened.

The approval relies on test outcomes remaining unused for selection. If that separation cannot be maintained or supported by the audit, the results will be reported as a descriptive backtest and no claim of independent held-out confirmation will be made.

## Decision

1. Retrospective evaluation. The test period is evaluated once, after the late tag. Results are described as a retrospective held-out evaluation, not as forecasts issued prospectively on 7 to 8 November, and not as evidence of live operational performance.

2. Selection data rule (by receipt time, not by origin date alone).
   - Fold training: features and outcomes with `collected_at_utc` strictly before 00:00 local of the fold's validation day (Wed 4, Thu 5, Fri 6 Nov).
   - Validation features: only values available at each origin's simulated prediction time. Validation outcomes may be received later, but only outcomes received strictly before 6 Nov 22:00 local (17:00 UTC) may influence selection.
   - Final fit: the same cut-off, 6 Nov 22:00 local (17:00 UTC), strict on `collected_at_utc`.
   - Imputation, scaling, winsorising and any other learned transformation are fitted inside the training folds only.
   - The selection script must reject any test-origin row and any outcome received at or after the cut-off. This guard and its regression test must be implemented and verified before model selection is run.

3. Candidates and criterion (unchanged from the protocol; no new options).
   - Models: Ridge alpha `{0.1, 1, 10, 100}`; HistGradientBoosting `max_depth` `{3, 5}` x `learning_rate` `{0.05, 0.1}`. Persistence is the benchmark and is not tuned.
   - Two feature sets, each tuned separately: full and matched no-weather.
   - Folds: validation days Wed 4, Thu 5, Fri 6 Nov, expanding training.
   - Criterion: mean over the three folds of the per-fold RMSE (equal fold weights), computed on the primary sample (native three-hourly origins selected by the UTC valid-time grid, exact same-city `t -> t+6 h` matching, original receipt timestamps, pilot and recovery records excluded). Hourly rows are used only in the sensitivity analysis.
   - Aggregation: per-fold RMSE first, then the unweighted mean. A fold with no eligible origins stops the selection (no silent skipping).
   - Tie-breaking, fixed before the selection script is written or run: if the mean CV RMSE of two settings is equal when rounded to 4 decimals (µg/m³), prefer the simpler one: Ridge over HistGradientBoosting; within Ridge the larger alpha; within HistGradientBoosting the smaller `max_depth`, then the smaller `learning_rate`. The rule is deterministic, is applied separately to each feature set, and introduces no additional performance metric.

4. Independence from the test. Test outcomes, plots, summaries and error patterns must not influence any choice. Both configurations needed for the full versus no-weather comparison are frozen before the test is opened.

5. Freeze. The selection code, candidate settings, CV table, the selected configuration for each feature set and the data-manifest hashes are committed and tagged with the real date and time of that commit, labelled `late freeze`.

6. Test. The original test period is evaluated once after the tag: the two frozen models and persistence on identical eligible origins. No retuning, no change of feature set, no new winner after seeing test results. Any later correction or extra analysis is recorded separately as post-test work.

7. Reporting. The report states the missed deadline and the actual selection, fitting and tagging times next to the Rule B and "weather adds information" results, which stay exploratory pilot screening results. Missing and ineligible pairs are reported separately from collected rows.

## Record of actual times

Entries are added by later commits when each event happens. They are not back-dated, and this file's history is not rewritten.

| Event | Date and time (Asia/Tashkent) | Commit |
|---|---|---|
| Planned freeze (protocol) | 2026-11-06 23:30 | - |
| Deviation reported to the Module Leader | 2026-11-08 | email |
| Written approval received | 2026-11-10 | email |
| This decision committed | see git log | see git log |
| Selection script committed | | |
| Selection run | | |
| Frozen configurations committed and tagged (`late freeze`) | | |
| Single test evaluation run | | |

## Consequences

The test result is weaker evidence than a prospective forecast would have been, and the report says so. The collector freeze (`0726522`) stays clearly separate from the later model freeze. History is preserved: nothing in the protocol or earlier commits is rewritten.