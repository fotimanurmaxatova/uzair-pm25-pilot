# 0012 - Freeze, evaluation and post-test implementation choices fixed before the selection run

Status: Proposed (accepted by the commit that records its date and time; must be committed BEFORE the first
assessed-snapshot selection run)

Related: decisions 0009, 0010, 0011; issues #8 and #15; analysis protocol.

## Context

Decision 0010 item 16 and decision 0011 section 8 require all freeze, evaluation, inference, error-analysis,
bootstrap, leave-one-city-out and EDA code, with synthetic regression tests, to exist before the `late-freeze` tag.
That code (`analysis/provenance.py`, `freeze.py`, `evaluate.py`, `q5_extras.py`, `inference.py`, `eda.py`) makes the
choices below. None of them was derived from any outcome value, CV result or test result; the test period has not
been loaded by any of this code. They change no candidate, fold, cut-off, criterion or tie-break rule.

## Choices

1. Freeze reads the latest numbered selection run only; an incomplete latest run stops it (0011 section 5). It checks
   the selection outputs, the six required code files (`analysis/cutoffs.py`, `data.py`, `modelling.py`,
   `selection.py`, `monitoring/coverage.py`, `monitoring/prepare.py`) and the snapshot against that run's manifest.
   The selection manifest must contain a `files` record `{path: {sha256, git_blob}}` and `snapshot_sha256`.
2. Artefacts: one pickle per primary model (loaded only after its SHA-256 matches the freeze manifest), a readable
   JSON description, `frozen_config.json` (selected configurations, selected-model fold RMSEs, persistence fold
   RMSEs) and `freeze_manifest.json` (written last, never overwritten).
3. Evaluation guard: exactly one annotated tag `late-freeze-YYYYMMDD-HHMM`; its commit is an ancestor of HEAD; clean
   tree; every commit after the tag touches only `results/`, `docs/`, `README.md` or `.gitignore` (checked per
   commit); the freeze manifest equals the manifest in the tag commit; artefacts, snapshot and frozen code files
   match their hashes; NumPy and scikit-learn match the pins. The marker `results/evaluation/FIRST_TEST_EVALUATION.json`
   is created exclusively before the test rows are loaded, so a crashed first run still counts as spent. A second run
   needs `--post-test` and writes to `results/post_test/<UTC stamp>/`, labelled post-test work.
4. Test eligibility: a primary test pair needs a usable pair (lags and target by exact valid time), an origin PM2.5
   value, and lag rows received strictly before the origin row (0010 item 26). Losses are counted separately from
   collected rows and from the maximum (112 native, 336 hourly).
5. Rule B uses the selected models' CV fold RMSEs and the persistence fold RMSEs from the selection run; "at least 10%
   below persistence" means skill >= 0.10; wins are strict.
6. Hourly sensitivity refits the frozen hyperparameters on all eligible hourly training pairs of `train_final`.
7. Error analysis: residual = observed - predicted; local hour is the hour of the forecast origin; observed-level bins
   <15, 15-35, 35-50, >=50 ug/m3; event thresholds 35 (primary), 25 and 50; missed event, false alarm, hit and
   correct negative as defined in `analysis/q5_extras.py`.
8. Paired block bootstrap: common six-hour blocks counted from the first test origin (7 blocks), all cities resampled
   together, 9,999 replications, seed 20261122, percentile 95% intervals of RMSE differences and skill.
9. Leave-one-city-out: frozen hyperparameters; training on the other seven cities' eligible native pre-cut-off pairs;
   one-hot columns for the seven training cities only, held-out city all zeros; imputation, winsorising and scaling
   fitted on those seven cities.
10. Q1 to Q4: clusters are local calendar days; city dummies without intercept; complete cases (dropped rows counted);
    Q2 regressor is humidity/10; Q4 outcome is 100 x the indicator (percentage points). Restricted wild cluster
    bootstrap, null imposed, t statistic, Webb weights, 9,999 replications, seed 20261123, p = share of |t*| >= |t|.
    The 95% interval is the symmetric bootstrap-t interval from the unrestricted wild bootstrap (seed + 1); it is
    labelled as such. Holm adjustment over Q1 to Q4 (Q3 = wind coefficient) is shown and enters no rule.
11. Rule A is evaluated on the Q3 wind coefficient over the primary run plus nine sensitivity runs (seven
    leave-one-day-out, weekday-only, all hourly rows). Any run that cannot be estimated, or any sign change, gives
    "inconclusive"; otherwise <= -2 is "worth a longer study", between -2 and 0 "below practical threshold", >= 0 "no
    support".
12. EDA: six charts. `pre_freeze` uses only the receipt-time-guarded loader; `full` needs the marker and is labelled
    "full window, after test evaluation".

## Consequences

Any change to these choices after the selection run is recorded as post-test work. The report states them next to
the results.

## Record of actual times

| Event | Date and time (Asia/Tashkent) | Commit |
|---|---|---|
| Decision committed | | |
