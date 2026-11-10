# Analysis protocol (fixed before assessed collection)

Source of truth: Version 4 proposal, the addendum and the approval email of 28.10.2026
(docs/approval/approval-record.md). Written down here, as the approval requires, before
assessed collection starts. Any change needs written agreement from the Module Leader and a
decision record.

## Scope
Seven-day exploratory pilot, eight cities (Tashkent, Samarkand, Bukhara, Andijan, Namangan,
Fergana, Nukus, Urgench). Hourly polls at :05, Mon 2.11 00:05 to Sun 8.11 23:05
(Asia/Tashkent, UTC+5; stored in UTC). Maximum 1,344 city-hours; target at least 1,000 valid
scheduled rows (collection coverage, not the number of analytical rows). Pilot and recovery rows
are excluded from the main analysis. Primary analysis: native three-hourly valid times only;
all eligible hourly rows are a labelled sensitivity analysis (see the clarification below).

## Definitions
- Unit: one city and one air-quality valid time (decision 0002).
- Class hours: 08:00 to 17:59 local time (Asia/Tashkent), Monday to Friday only (Q4 uses the
  five weekdays 2 to 6 Nov, so five day-clusters).
- High-PM2.5 (research threshold, not a safety threshold): modelled PM2.5 >= 35 ug/m3; 25 and
  50 for sensitivity. The EPA 35 value is a 24-hour standard; no equivalence is claimed.
- Target: the same city's modelled PM2.5 at exactly t + 6 h (match by valid time, never row
  position). Origins whose outcome falls after the last poll stay unscored.
- A training outcome is usable only if it was received (collected_at_utc) by the fitting cut-off.

## Questions (city fixed effects in every model)
| Q | Model | H0 | Effect measure |
|---|---|---|---|
| Q1 | PM2.5 = a_city + b*wind | b = 0 | ug/m3 per +1 m/s |
| Q2 | PM2.5 = a_city + b*humidity | b = 0 | ug/m3 per +10 percentage points |
| Q3 | Q1 + temperature, humidity, precipitation, hour of day (sin/cos) | b_wind = 0 | ug/m3 per +1 m/s |
| Q4 | 1{PM2.5 >= 35} = a_city + d*class_hours (weekdays only) | d = 0 | probability difference, percentage points; 5 clusters |
| Q5 | persistence; full model; matched no-weather model; each with Ridge and HistGradientBoosting | - | RMSE, MAE, R2, skill vs persistence |

Inference: wild cluster bootstrap by calendar day (all cities in one cluster, Webb weights).
All p-values and intervals are exploratory and conditional on their assumptions; Holm-adjusted
values are shown for transparency and enter no rule.

## Features (Q5)
- Full model: PM2.5 at t, t-3 h, t-6 h (exact valid time, same city); NO2; hour of day (sin, cos);
  temperature, relative humidity, precipitation, wind speed, wind direction (sin, cos), surface
  pressure, 3-hour pressure change; city. No weekend flag (test is weekend only).
- No-weather model: the same list without the weather variables (temperature, humidity,
  precipitation, wind speed, wind direction, pressure, pressure change).
- Imputation, scaling and winsorising are fitted inside training folds only; test outcomes are
  never altered. Grids (from Version 3): Ridge alpha {0.1, 1, 10, 100}; HistGradientBoosting
  max_depth {3, 5} x learning_rate {0.05, 0.1}; same procedure for full and no-weather models.

## Calendar (Asia/Tashkent)
- CV: three expanding folds, validation days Wed 4, Thu 5, Fri 6 Nov (origins 00:00 to 15:00);
  each fold fitted with a cut-off of 00:00 on its validation day (last training origin = cut-off - 7 h).
- Final fit cut-off Fri 6 Nov 22:00 (training origins 2 Nov 00:00 to 6 Nov 15:00). Model,
  hyperparameters and preprocessing frozen and tagged by 6 Nov 23:30; no refit afterwards.
- Test origins Sat 7 Nov 00:00 to Sun 8 Nov 17:00 (maximum 336 pairs). A weekend-only test after
  weekday training is not evidence for a typical week. Report collected rows and eligible
  pairs separately.

## Screening rules (exploratory; no significance gate)
- Rule A: the low-wind indicator is "worth a longer study" if the Q3 estimate b_wind <= -2
  ug/m3 per m/s and stays negative in all sensitivity runs (leave-one-day-out, weekday-only,
  all eligible hourly rows). Unstable sign: inconclusive. Between -2 and 0: below practical threshold.
  At 0 or above: no support. A sensitivity run that cannot be estimated makes the result inconclusive.
- Rule B: the full model is "promising" if test RMSE is at least 10% below persistence and it
  wins in at least 2 of 3 CV folds. Weather adds information only if it also beats the matched
  no-weather model on the test and in at least 2 of 3 folds. The test is never used to choose a configuration.
- Passing a rule supports a longer evaluation only; it is not a causal or general-forecasting claim.

## Fallback (unchanged from the addendum)
Day 3: fewer than 400 valid rows -> fix scheduler or host. Day 7: 1,000 or more -> full plan;
700 to 999 -> same questions, wider uncertainty; fewer than 700 -> contact the Module Leader
before any change. Dropping Q4 or Q5 only under an alternative agreed in writing.

## Clarification of the native three-hourly analysis (Module Leader email, 3 November 2026)
Added in a new dated commit; earlier commits are preserved. The Module Leader's email names this
document as `docs/analysis-plan.md`; in this repository it is `docs/protocol/analysis-protocol.md`.
Analytical definitions, thresholds and split rules are unchanged. This clarification replaces the
earlier wording that listed "native-step-only" as a sensitivity run (a drafting error).
- Primary analysis: native three-hourly valid times for all statistical analysis and for model
  training, validation and testing. Native times are selected by the source's UTC valid-time grid
  (valid time divisible by 3 hours, stored as `is_native_step`), never by taking every third
  stored row.
  Validation origins are the native three-hourly valid times that fall within the specified
  local 00:00-15:00 window, selected using the source UTC valid-time grid.
- Sensitivity analysis: repeat the analysis with all eligible hourly rows, with the same
  chronological boundaries, feature definitions and availability rules. Report these results
  separately and label them as sensitivity results.
- The primary configuration follows this rule, not whichever run gives stronger results.
- Six-hour target: exact t to t+6 h matching on valid time. A missing outcome stays missing; the
  next available row is never substituted.
- Collection target: hourly collection continues. The 1,000-row target concerns collection
  coverage. Hourly coverage, native-step sample sizes and usable forecast pairs are reported
  separately.
- Native-step sampling does not remove temporal or spatial dependence; the dependence-aware
  methods above (wild cluster bootstrap by calendar day) stay in force.
- Expected maximum sample sizes (derived by arithmetic from the calendar above; actual usable
  pairs are reported after missingness and lag construction): native valid times fall at local
  02:00, 05:00, 08:00, 11:00, 14:00, 17:00, 20:00, 23:00. Validation origins from 00:00 to 15:00
  contain 5 native origins per city and day; the weekend test origins (Sat 00:00 to Sun 17:00)
  contain at most 14 per city (112 over eight cities), against 336 hourly origins.
