# Checkpoint 3: Statistical analysis and decision support

**Tag:** `cp3-submission`  
**Full commit hash:** Recorded in `docs/checkpoints/evidence-register.md` in a commit made after the tag (a commit cannot contain its own hash).  
**Issues:** #8 late model freeze, #15 selection script with receipt-time guard, #17 guarded analysis data layer, #18 single test evaluation script  
**Decisions:** 0009, 0010, 0011, 0012  
**Freeze tag:** `late-freeze-20261125-0954` (commit `817614f67f39894fecf5795b63fb7cb7d3c0924b`)

## Value statement

This component enables the university student support and campus safety office to decide whether a longer prospective study of weather-based PM2.5 monitoring is justified. It uses a guarded and reproducible workflow covering receipt-time model selection, final fitting and freeze, one retrospective held-out evaluation, Q1–Q4 statistical inference, and exploratory screening under predefined Rules A and B.

The workflow produces an auditable evidence base and two explicit screening outcomes:

- **Rule A — no support:** the primary Q3 wind estimate was positive (+0.99 µg/m³ per m/s), rather than meeting the predefined negative-effect threshold of −2 µg/m³ per m/s. All nine sensitivity estimates were also positive.
- **Rule B — not promising:** the full model achieved 8.4% skill against persistence, below the predefined 10% threshold, and did not outperform the no-weather model on the held-out test set.

The specific benefit is a documented, reproducible screening decision about whether a longer study is justified, rather than an unsupported operational, causal, public-health or safety claim. These are exploratory pilot results and do not establish general forecasting performance.

## What this checkpoint covers (brief: statistical analysis and decision support)

| Requirement | Evidence |
|---|---|
| Analysis protocol defined before the assessed collection period | `docs/protocol/analysis-protocol.md` (prepared before 2 November 2026); Decisions 0009–0012 record the analysis rules and subsequent approved amendment |
| Model selection without test-period leakage | `analysis/selection.py`, `analysis/data.py`, `results/selection/run-001/`; three expanding validation folds, native three-hourly primary analysis and strict receipt-time cut-offs |
| Selection guard and temporal safeguards | `tests/test_selection.py`, `tests/test_analysis_data.py`, `tests/test_guards.py`; tests reject test-origin rows and outcomes unavailable by the relevant cut-off |
| Final fit and freeze | `analysis/freeze.py`, `analysis/provenance.py`, `results/freeze/`; frozen configurations, model artefacts and hash-recorded manifest |
| Auditable late freeze | Annotated tag `late-freeze-20261125-0954`, pointing to commit `817614f67f39894fecf5795b63fb7cb7d3c0924b` |
| Single held-out evaluation | `analysis/evaluate.py`, `results/evaluation/`; durable `FIRST_TEST_EVALUATION.json` marker and evaluation manifest |
| Benchmarks and matched comparison | Full, no-weather and persistence models evaluated on the same 88 eligible native test pairs (`test_metrics.json`) |
| Statistical inference | `analysis/inference.py`, `results/inference/inference.json`; wild cluster bootstrap using Webb weights, confidence intervals and Holm adjustment |
| Uncertainty and robustness | Paired block bootstrap, leave-one-city-out analysis, hourly sensitivity, leave-one-day-out and weekday-only sensitivity analyses |
| EDA and visualisation | `results/eda/pre_freeze/` and `results/eda/full/`; six charts in each mode, with manifests |
| Decision support | Rule A and Rule B applied using the predefined protocol thresholds |
| Automated tests | 286 tests passed in the recorded full-suite verification (`python -m pytest -q`) |

## Results (assessed snapshot, retrospective held-out evaluation)

All three models were scored on the same 88 eligible native three-hourly test pairs.

| Model | RMSE (µg/m³) | MAE (µg/m³) | R² | Skill vs persistence |
|---|---:|---:|---:|---:|
| Persistence | 8.87 | 6.50 | −0.04 | 0.0% |
| Full (Ridge, α = 10) | 8.12 | 6.22 | 0.13 | +8.4% |
| No-weather (HGB, depth = 3, learning rate = 0.05) | 7.37 | 5.47 | 0.28 | +16.9% |

Of the 112 possible native test origins (14 per city), 104 were collected and 88 had an eligible usable t+6 h pair. The exclusion pattern was identical across all eight cities, verified against the assessed snapshot:

| Local date | Possible origins | Collected origins | No collected t+6 h target | Origin not collected |
|---|---:|---:|---:|---:|
| 7 Nov 2026 | 64 | 64 | 0 | 0 |
| 8 Nov 2026 | 48 | 40 | 16 | 8 |
| **Total** | **112** | **104** | **16** | **8** |

On 8 November, the 11:00 and 14:00 local origins were collected in every city, but their t+6 h targets were not collected (16 pairs in total). The 17:00 local origin was not collected in any city (8 origins). All 24 exclusions therefore occurred on 8 November; none occurred on 7 November. This pattern is consistent with the shared end-of-window collection gaps recorded in `docs/incidents/2026-11-08-missed-polls.md`. The incident report records two missed scheduled polls at 17:05 and 18:05 local time, but states that their root cause is unknown; no specific cause, such as laptop sleep, is inferred here. No usable feature row was received at or after its prediction time.

The hourly sensitivity analysis is reported separately: 302 of 336 possible hourly pairs were usable.

## Sample sufficiency

The approved collection target of at least 1,000 valid scheduled rows out of 1,344 was met: 1,311 valid rows (97.5%). This is a collection target, not a statistical power claim.

The analytical samples are smaller and temporally clustered. Q1–Q3 use 424 native three-hourly rows across 7 day-clusters; Q4 uses 312 weekday rows across 5 clusters; and the held-out evaluation uses 88 eligible native pairs out of a possible 112, covering two weekend days.

The sample is considered sufficient only for the approved exploratory screening purpose. It does not support claims of precise effects, general forecasting performance or independence between observations.

### Rule B — predictive screening

The full model's test skill against persistence was 0.084, below the predefined 0.10 threshold. Although the full model beat persistence in all three validation folds, it beat the matched no-weather model in only two of the three folds and did not beat it on the held-out test set.

The no-weather model had lower held-out RMSE and MAE than the full model. Rule B therefore returned `promising=false` and `weather_adds_information=false`.

The paired block-bootstrap 95% intervals for the skill of both predictive models include zero. The protocol specified seven common six-hour test blocks (Decision 0012, item 8). Although origin observations were present in all seven blocks, the final block contained eight city-level origins without corresponding t+6h target observations. Consequently, only six blocks contained eligible evaluation pairs and were included in the paired block bootstrap (9,999 replications; seed 20261122). The resulting intervals are indicative only, given the two-calendar-day test window. The evidence does not show that adding weather variables improves this pilot's predictive performance.

### Rule A — wind-effect screening

The primary Q3 wind coefficient was approximately +0.99 µg/m³ per m/s, with a 95% bootstrap-t interval of approximately +0.16 to +1.81. The nine sensitivity estimates were also positive, ranging approximately from +0.59 to +1.22.

The predefined threshold was −2 µg/m³ per m/s. The primary estimate and all nine sensitivity estimates were on the opposite side of zero from the hypothesised negative effect. Rule A therefore returned `no support`.

### Q1–Q4 inference

| Question | Estimate | 95% bootstrap-t interval | Sample / clusters |
|---|---:|---:|---:|
| Q1 | +0.81 | −0.11 to +1.72 | 424 / 7 |
| Q2 | +1.74 per +10 percentage points humidity | +0.86 to +2.62 | 424 / 7 |
| Q3 | +0.99 per m/s wind | +0.16 to +1.81 | 424 / 7 |
| Q4 | −9.80 percentage points in class hours | −14.83 to −4.78 | 312 / 5 |

Holm-adjusted p-values ranged from approximately 0.014 to 0.042.

Q1 illustrates why the p-value and confidence interval must both be reported: its wild-cluster restricted p-value is approximately 0.021, while its symmetric bootstrap-t interval includes zero. These procedures answer related but not identical inferential questions; the p-value should not be presented as proof of a stable non-zero effect.

Q4 uses five weekday clusters. With five clusters, only 7,776 distinct Webb-weight combinations are available, fewer than the 9,999 requested replications; some combinations are therefore repeated. This further limits the reliability of the inferential result.

The estimates describe associations in the pilot data. They do not establish causal effects.

## Independent test specification

- **Purpose:** verify that the analysis is reproducible, respects the frozen protocol and temporal safeguards, and preserves the single-use held-out evaluation.
- **Inputs:** `snapshots/assessed_snapshot.db`, committed `results/` artefacts, and synthetic fixtures in `tests/`.
- **Reference environment:** Python 3.12.3 with the repository's pinned dependencies. The separately recorded Linux clean-checkout verification used Python 3.13.18; these are distinct verification environments.

### Clean-checkout commands

Windows CMD:

```cmd
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pytest -q
```

Linux/macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
```

### Acceptance criteria

1. The automated test suite passes.
2. Selection and data-layer guards reject test-origin rows and outcomes received at or after the applicable cut-off.
3. The selection and freeze manifests identify the expected inputs and artefacts, and recorded hashes match.
4. The annotated `late-freeze-*` tag points to the frozen commit and is an ancestor of the evaluation commit.
5. The first-evaluation marker exists and identifies the correct tag, tag commit and snapshot.
6. The first held-out evaluation is performed only once; later work uses the post-test workflow.
7. Collected origins, usable pairs and eligible pairs are reported separately.
8. Post-test inference and full-window EDA are identified as post-test outputs.

### Recorded verification

The independent clean-checkout verification was performed from the `cp3-submission` tag in a fresh Linux clone using Python 3.13.18 and a fresh virtual environment.

| Verification | Expected result | Actual result |
|---|---|---|
| Dependency installation | Pinned requirements install successfully | Completed |
| Full automated test suite | All tests pass | 286 passed in 41 seconds |
| Snapshot verification (`uzair.cli verify`) | All raw responses verified; no hash mismatches | 2,638 raw responses processed; 0 hash mismatches |
| Duplicate-run integrity guard | Existing selection run prevents an unintended second run | Correctly refused a second run because `run-001` already existed |
| Q1–Q4 inference | Results reproduce the recorded estimates and Holm-adjusted results | Matched within 1e-12 |
| EDA workflow | EDA completes and produces chart outputs | Six charts were reported in the clean-checkout run; the specific EDA mode was not recorded |
| Post-test evaluation | Recorded held-out metrics and Rule B outcome are reproduced without rerunning the first evaluation | Metrics and Rule B outcome reproduced; outputs written to `/tmp` |

These were post-tag verification checks. They did not modify the frozen submission tag or rerun the first held-out test evaluation. The detailed terminal output for this Linux verification was not retained.

### Additional clean-checkout verification (Windows, 26 November 2026)

A separate verification was performed from the annotated `cp3-submission` tag in a fresh Windows clone using Python 3.12.6 (the project requires Python >=3.10).

The full terminal record is retained in `docs/checkpoints/cp3-clean-checkout-2026-11-26.txt`.

| Verification | Actual result |
|---|---|
| Dependency installation | All project dependencies installed successfully |
| Full automated test suite | 286 passed in 104.89 seconds |
| Snapshot verification | 2,638 raw responses checked; 0 hash mismatches |
| Integrity dry-run | Successful using a separate output path; the existing `results/selection/run-001` correctly prevented an unintended duplicate run |
| Full-window EDA | Six charts generated from 1,311 rows |
| Post-test evaluation | Completed with 88 eligible primary native pairs |
| Final Git state | Clean working tree |

The post-test evaluation reported:

- Full model: RMSE 8.1223, MAE 6.2230, skill 0.0842.
- No-weather model: RMSE 7.3725, MAE 5.4661, skill 0.1687.
- Persistence: RMSE 8.8687, MAE 6.4977, skill 0.0000.
- Rule B: `promising: false`; `weather_adds_information: false`.

The original single held-out test evaluation was not rerun. The post-test evaluation was explicitly labelled as post-test work and its generated artefacts were preserved outside the clean checkout after verification. The existing selection output and frozen submission files were not modified.

The Windows verification used a detached checkout at the annotated `cp3-submission` tag, as expected. The integrity dry-run used a separate output path because the existing `run-001` directory was already present; no new selection run was created.

The first held-out evaluation marker records the original evaluation time as 25 November 2026 at 11:25:42 Tashkent time. The evaluation manifest records the freeze tag and assessed snapshot hash. The original evaluation was not rerun during the subsequent post-test analysis.

The pre-selection integrity command was invoked after `results/selection/run-001/` already existed. It correctly refused to plan another selection run without both `--rerun` and a non-empty `--reason`. No rerun was requested, and the existing selection output was preserved. This is the expected duplicate-run protection in that state, not evidence that the snapshot or frozen model artefacts were corrupted.

## Substantive change since Checkpoint 2

Checkpoint 2 established reliable collection, data-quality monitoring, snapshot verification and stakeholder queries.

Checkpoint 3 adds the CP3 analysis pipeline:

- `analysis/` modules for cut-offs, the guarded data layer, model selection, freeze, provenance, evaluation, inference, Q5 analyses and EDA.
- Decisions 0010–0012 and the approved late-freeze amendment recorded in Decision 0009.
- Numbered selection outputs, frozen configurations and model artefacts, evaluation outputs, inference results and EDA charts under `results/`.
- Automated tests covering temporal cut-offs, leakage prevention, provenance, selection, freeze, the selection-to-freeze workflow, single evaluation, inference and EDA.

The test suite increased to 286 passing tests in the recorded verification. The exact change in test count since CP2 should be described using the committed CP2 and CP3 states, rather than inferred from the current working tree.

## Failures, deviations and corrections (traceability evidence)

- **Missed planned freeze:** the planned freeze deadline was 6 November 2026 at 23:30 Tashkent time. The delay was reported to the Module Leader on 8 November, and a retrospective held-out evaluation amendment was approved on 10 November and recorded in Decision 0009.
- **Actual selection and freeze timeline:** the selection run started on 25 November 2026 at 08:46:46 Tashkent time. Its commit is `dbac3ff` (record the commit timestamp separately where required). The late freeze was committed at 09:54:42 Tashkent time as `817614f`. The first held-out evaluation marker records 11:25:42 Tashkent time and is associated with commit `7297549`.
- **Aggregate test-period exposure:** aggregate PM2.5 information had been viewed through monitoring scripts before the freeze. This is disclosed in Decision 0009. The evaluation protocol and report distinguish this prior aggregate exposure from access to per-origin test outcomes and from the later held-out model evaluation.
- **Post-test work:** inference, full-window EDA, bootstrap and leave-one-city-out analyses were performed after the first held-out evaluation and are retained as post-test work.
- **Integrity dry-run after selection:** `analysis.integrity` returned a duplicate-run refusal because `run-001` already existed. No second selection was started, and the existing selection output was preserved.
- **Bootstrap block-count clarification:** Decision 0012 item 8 specifies seven common six-hour test blocks. The snapshot contains origin observations in all seven blocks. However, the eight origins in the final block (2026-11-08 09:00 UTC, across all eight cities) have no corresponding t+6h target observations and therefore produce no eligible evaluation pairs. The paired block bootstrap consequently uses six populated eligible blocks, as recorded in `results/evaluation/block_bootstrap.json` (`blocks: 6`; 9,999 replications; seed 20261122). This is a data-availability limitation in the final test block, not a claim that the protocol specified only six blocks.

## Known limits / next step (CP4)

- The planned freeze date was missed. The evaluation is retrospective, not a prospective operational forecast.
- The held-out test period is short and contains 88 eligible native pairs.
- There are only seven clusters for Q1–Q3 and five for Q4; uncertainty estimates and p-values should therefore be interpreted cautiously.
- The full and no-weather models were selected separately and belong to different model families (Ridge and HGB). The comparison is a comparison of the selected pipelines, not a controlled experiment isolating weather features within an otherwise identical model.
- The full model did not meet the 10% Rule B threshold and did not outperform the no-weather model on the held-out test set.
- Q1's restricted wild-cluster p-value and symmetric bootstrap-t interval give different significance indications; both are reported transparently.
- Q4's five-cluster bootstrap repeats Webb-weight combinations.
- The results are exploratory and do not establish causal effects, safety conclusions or general forecasting performance.
- Request accounting and its limits are documented in `docs/checkpoints/cp2.md` (section "Request accounting and retry-timing limits"), including the 8 unpaired air-quality responses and the frozen collector's retry-timing limitation.

CP4 will focus on integrating the system, including the dashboard/API, final attribution (issue #7) and the final project report.

## AI assistance in this period

See `docs/ai/ai-log.md` for the dated record of AI assistance. The log distinguishes limited review and guidance from the project code, tests, selection, freeze operations, Git actions, statistical analysis and substantive documentation prepared and carried out by the student.
