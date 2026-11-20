# 0010 - Analysis implementation choices fixed before model selection

Status: Proposed (becomes Accepted when committed; the commit time is the record)

Related: decision 0009, analysis protocol, GitHub issues #8 and #15; monitoring reconciliation: GitHub issue #16. Additional issues to be created: single test evaluation script with late-freeze guard; Q1-Q4 inference and EDA.

## Context

Decision 0009 fixes the candidates, grid, folds, cut-offs, criterion and tie-break rule. It does not fix implementation details of preprocessing and of the sensitivity and inference steps. Those details are fixed here, before the selection script is run, so that no choice can be made after seeing CV or test results. None of them is tuned. If a detail below proves unworkable, the change is recorded as a new decision before the selection run; after the selection run it is recorded as post-test work.

## Monitoring independence

As disclosed in Decision 0009, aggregate monitoring outputs covering the collection period, including the test period, were viewed before model selection. These outputs comprised:

- Coverage summaries;
- Data-quality audit summaries;
- Stakeholder query summaries;
- Request, retry, failure and retained-response reconciliation summaries.

No PM2.5 outcome values, outcome distributions, error summaries, plots or model-performance results from these aggregate outputs were used to choose features, preprocessing methods, thresholds, hyperparameters or model candidates.

One hyperparameter setting did use aggregate count information: `min_samples_leaf=5` (item 10) was set with the number of usable primary training pairs per fold in mind. The approximate smallest training-fold count of 64 was read from the count-only output of `monitoring.prepare` (`cv1_train=64`). The protocol calendar gives the same order of magnitude. This count describes sample size, not PM2.5 outcomes or model errors. The setting was made before any model was fitted, is fixed, and is not tuned. 

The monitoring outputs were also used for collection monitoring and data-quality accounting. The scripts and available monitoring evidence are retained in the repository.

## Data and sample

1. Source: the committed snapshot `snapshots/assessed_snapshot.db` (SQLite online-backup copy of the live collection; source database SHA-256 `d078c74161aeaba5dfda474070dfae71d7de4df58aacce6673b44e0ae8091256`, snapshot SHA-256 `9ff58bb40ffc09ed2a7ff929d7a2f6ecce85b12b9c5bcdf55ef427ae1693d6c2`), read-only.

2. Rows: scheduled, non-pilot observations only. Lags (t-3 h, t-6 h), the pressure change and the target (same city, t+6 h) are matched by exact valid time; a missing match stays missing (`monitoring/prepare.py`).

3. Primary sample: native three-hourly origins (UTC valid-time grid) with an existing t-3 h lag, t-6 h lag and t+6 h target. Hourly origins form the sensitivity sample.

4. Receipt-time rule (0009): fold training features and outcomes must have `collected_at_utc` strictly before that fold's validation-day 00:00 Asia/Tashkent cut-off. Validation features must be available at the simulated prediction time. Validation outcomes may be received later, but are eligible for selection only if received strictly before the final selection cut-off of 6 November 2026 22:00 Asia/Tashkent (17:00 UTC). The final-fit features and outcomes must also be received strictly before this final cut-off. The selection code enforces these rules itself and fails if any test-origin row is loaded or any ineligible outcome is used.

## Preprocessing (fitted inside the training part of each fold only)

5. Features: the full and the no-weather lists of the protocol. City enters as one-hot indicators in all models.

6. Missing feature values: replaced by the training-fold median. Targets are never imputed or altered.

7. Winsorising: continuous numeric features only (including PM2.5 lags, pollutant and weather measurements, and pressure change). Each is clipped to the training-fold 1st and 99th percentiles. One-hot city indicators and all cyclic sin/cos features are not clipped.

8. Scaling: standardisation (training-fold mean and standard deviation) for continuous numeric features only, for Ridge. One-hot city indicators and cyclic sin/cos features are not scaled. HistGradientBoosting uses no scaling.

## Models (grid from the protocol; nothing else varies)

9. Ridge (`alpha` in {0.1, 1, 10, 100}), intercept included.

10. HistGradientBoosting (`max_depth` in {3, 5}, `learning_rate` in {0.05, 0.1}), with fixed `max_iter=100`, `min_samples_leaf=5`, `l2_regularization=0`, `early_stopping=False`, `random_state=0`.

    (`min_samples_leaf=5` replaces the library default of 20. It was set on 2026-11-16, before any model was fitted, because the smallest training fold has about 64 usable primary pairs; that count was read from the count-only output of `monitoring.prepare` (`cv1_train=64`) and is consistent with the protocol calendar. It was not chosen from any outcome value, error figure or plot. It is fixed and not tuned.)

    All parameters not named here are the defaults of the scikit-learn version pinned in `requirements.txt`.

11. Persistence: the forecast for t+6 h is the PM2.5 observed at t in the same city. Not tuned.

12. Selection: per feature set (full, no-weather) separately, among the eight candidates, by the mean of the three per-fold RMSEs on the native validation origins (0009). The CV table lists every candidate in every fold.

## Evaluation (once, after the late tag; 0009)

13. Metrics: RMSE, MAE, R2 and skill = 1 - RMSE(model) / RMSE(persistence). R2 is computed against the mean of the test targets and is reported with that definition.

14. The primary full and no-weather models are fitted on all eligible native training rows using the final-fit cut-off before the freeze. Their fitted artefacts, preprocessing state, configurations and SHA-256 hashes are included in the freeze commit and manifest. The first test evaluation uses these frozen artefacts for prediction only; it does not refit the primary models. All models and persistence are scored on the same eligible native test origins. The hourly sensitivity result uses the same frozen hyperparameters, refitted on all eligible hourly training rows with the same cut-off; no second selection is run. It is reported separately and labelled as sensitivity.

15. Rule B (protocol): the full model is "promising" only if its test RMSE is at least 10% lower than persistence RMSE and its RMSE is strictly lower than persistence in at least two of the three validation folds. "Weather adds information" is supported only if, in addition, the full model has strictly lower RMSE than the matched no-weather model on the same eligible test origins and in at least two of the three validation folds. Ties do not count as wins. Report the selected-model CV results as potentially optimistic because configurations were selected using those same folds; the untouched test result remains the primary evaluation.

16. The selection script and evaluation script are both written and tested using synthetic fixtures only, before the freeze. The freeze commit includes the selection code, evaluation code, their regression tests, the complete CV table, selected configuration files, fitted primary model artefacts, preprocessing state and SHA-256 manifest.

    The freeze commit is tagged with an annotated tag named `late-freeze-YYYYMMDD-HHMM` (Asia/Tashkent time of the freeze commit); the tag message repeats the commit hash and time. No backdating is permitted.

    The selection and final-fit code must enforce the receipt-time cut-offs and reject test-origin rows. The evaluation script refuses to run unless exactly one tag matching `late-freeze-*` exists, it is annotated, and its commit is an ancestor of HEAD; the working tree is clean before the first evaluation; all commits after the tag modify files only under `results/` and `docs/`, or the explicitly permitted root files `README.md` and `.gitignore`; and the configuration and model artefact hashes match the frozen manifest. It also refuses any test-origin data loaded during selection.

    The evaluation script writes a marker when the first test evaluation runs. A second run requires `--post-test` and labels all output as post-test work.

## Inference and exploratory analysis

17. Q1 to Q4 are descriptive associations, not predictions. They are run only after the single test evaluation and do not feed back into any choice made for Q5.

18. Q1 to Q3 use all primary native rows of 2 to 8 November; Q4 uses weekday rows of 2 to 6 November (five calendar-day clusters). Inference uses a restricted wild cluster bootstrap with the null imposed, a t-statistic and Webb six-point weights, 9,999 replications and a fixed seed. Holm-adjusted p-values are reported for transparency and do not enter any decision rule. The small number of clusters limits inferential reliability. For Q4, five clusters permit only 6^5 = 7,776 distinct Webb-weight combinations, so 9,999 draws necessarily repeat some combinations; this limitation is reported.

19. Robustness checks for Q1 to Q3 (Rule A): leave-one-day-out (each of the seven days omitted in turn), weekday-only (2 to 6 November) and all eligible hourly rows. The Rule A conclusion is drawn only if the sign is stable in all of them; a run that cannot be estimated makes the result inconclusive.

20. Q5 error analysis is performed after the single test evaluation. Report residual and absolute-error summaries by city, local hour and observed PM2.5 level. For the 35 µg/m³ event threshold, report missed events and false alarms; repeat the classification sensitivity analysis at 25 and 50 µg/m³.

    For uncertainty in paired test-performance differences, use a paired block bootstrap that resamples common six-hour time blocks across all cities together, with 9,999 replications and a fixed seed. This preserves the shared time blocks across cities. Because the test covers only two calendar days, these intervals are indicative and are not treated as reliable population-level confidence intervals.

    Q5 robustness checks include the eligible hourly sensitivity sample and leave-one-city-out (LOCO) refits using the frozen hyperparameters. For each LOCO run, one city is held out and evaluated on that city's eligible native test origins on 7–8 November 2026. The models are trained on eligible pre-cut-off native training rows from the other seven cities only. Both the full and no-weather feature sets are evaluated, with persistence as the baseline, on the same held-out-city test origins. The seven training cities have their own one-hot indicator columns; the held-out city is represented by all-zero values across those seven columns. LOCO is a post-freeze sensitivity analysis, not a replacement for the primary fitted models. No additional hyperparameter selection is performed.

    These additional Q5 analyses are planned post-test work. If time is short they are dropped and reported as not done; they are not replaced by other analyses.

21. EDA: before the freeze only on data received before the 6 November 22:00 Asia/Tashkent (17:00 UTC) cut-off; the full-window EDA (at least five labelled charts) is produced after the test evaluation and labelled as such.

## Sufficiency and limits (for the report)

22. Native primary counts: approximately 248 eligible training pairs for the final fit; approximately 64 training pairs in the smallest training fold; approximately 40 validation pairs per fold; and at most 112 test pairs, of which approximately 88 are expected to be usable. These are planning estimates based on aggregate coverage and missingness counts, not verified final usable-pair counts. Exact counts must be reported from the guarded preparation and selection outputs and the CV table. With seven calendar-day clusters (five for Q4), intervals are wide. The analysis is an exploratory pilot screen; effects are reported with their uncertainty, and the weekend-only test is not evidence for a typical week.

23. Reproducibility: fixed seeds, pinned package versions in `requirements.txt`, one command per stage, outputs written to `results/` with a manifest of SHA-256 hashes.

24. Description of the evaluation: a retrospective chronological holdout with a disclosed late freeze and prior aggregate monitoring. Rule B and "weather adds information" findings remain exploratory pilot screening results.

25. Reporting: usable and excluded pairs are reported by city and date; hourly and native pairs are not presented as independent observations; collected rows, logical requests, HTTP attempts and usable pairs are reported separately (see `docs/coverage/reconciliation-2026-11-16.txt`).

## Clarifications added on 2026-11-20, before any selection run

These clarifications were recorded before any model was fitted on the assessed data and before any cross-validation result was seen. The selection script had been drafted but had not been committed or run. These clarifications do not derive from any outcome value or model-performance result.

26. **Simulated prediction time and feature availability.** For a forecast origin \(t\), the simulated prediction time is the receipt time (`collected_at_utc`) of the origin row. The origin features are those recorded in that row. The lag rows at \(t-3\) h and \(t-6\) h, including the \(t-3\) h row used to calculate the three-hour pressure change, must have been received strictly before that prediction time. Otherwise, the pair is not eligible and the exclusion is reported separately. For fitted partitions, the origin row, both lag rows and the target outcome row must also have been received strictly before the relevant fold cut-off. An outcome received exactly at or after that cut-off is ineligible for fitting.

27. **Preprocessing order.** The fixed order is median imputation (including cyclic features), winsorisation of continuous numeric features, and standardisation for Ridge. Imputation medians, winsorisation bounds (1st and 99th percentiles, using NumPy's default linear percentile method) and scaling statistics are computed using the training data of the relevant fold only. Winsorisation bounds are computed on the imputed training values. A zero standard deviation is replaced by 1. A feature with no observed training value causes the run to stop. One-hot city indicators and cyclic sin/cos features are not winsorised; they are not standardised for Ridge.

28. **Strict receipt-time comparison.** The monitoring scripts `monitoring/coverage.py` and `monitoring/prepare.py` use an inclusive `<=` comparison for the relevant outcome receipt-time cut-offs. The analysis implementation uses the strict `<` comparison required by Decision 0009. On the assessed snapshot, the compared monitoring and analysis counts are identical for the corresponding partitions, and the new feature-availability checks exclude zero pairs. The strict analysis rule remains authoritative for model selection and fitting.

## Consequences

The selection and evaluation code, regression tests, CV table, selected configurations, fitted primary model artefacts, preprocessing state and their SHA-256 manifest are committed before the annotated `late-freeze-YYYYMMDD-HHMM` tag is created. Both scripts are tested only with synthetic fixtures before the freeze. The first test evaluation is permitted only after the unique annotated freeze tag exists and the evaluation guard passes. All post-freeze commits are restricted to `results/`, `docs/`, and the explicitly permitted root files `README.md` and `.gitignore`. No test result may be used to change the frozen models, features, preprocessing, thresholds or hyperparameters.
