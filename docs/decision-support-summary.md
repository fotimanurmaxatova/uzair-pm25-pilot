# UzAir pilot: decision-support summary for the student support and campus safety office

Weather data by Open-Meteo.com (CC BY 4.0); air quality from CAMS Global via the Open-Meteo Air Quality API. PM2.5 values are modelled grid-cell estimates, not station readings; all statistics are derived from them.

## The decision

Should the office add a low-wind indicator and a six-hour-ahead PM2.5 prediction to its outdoor-activity advisory, or is a longer evaluation needed first?

## What we did

Our own collector polled eight Uzbek cities hourly from 2 to 8 November 2026: 1,311 valid city-hours of 1,344 possible (97.5%). Models and tests were fixed before the held-out weekend (7–8 November) was scored. The model freeze was made late (25 November), and the test is a retrospective evaluation, not live forecasting. Results are exploratory pilot screening.

## What the evidence shows

- Forecast skill. On 88 eligible three-hourly forecasts, simply repeating the latest reading had RMSE 8.87 ug/m3. The weather model scored 8.12 (8.4% better, below our 10% bar). A model without weather scored 7.37 (16.9% better).
- Does weather add information? No: the no-weather model did at least as well as the weather model.
- Wind. Across the week, higher wind speed was associated with slightly higher, not lower, PM2.5 (+0.99 ug/m3 per m/s; 95% bootstrap-t interval +0.16 to +1.81). The pre-specified rule required a drop of at least 2 ug/m3 per m/s, so there is no support for a low-wind indicator.
- High readings (research threshold 35 ug/m3). Only 4 of 88 targets reached 35. Every method caught 1 and missed 3; false alarms were 6 (weather model), 5 (no-weather) and 5 (repeat latest reading). At 25 ug/m3 (10 events) the weather and no-weather models caught 9 and 10, persistence 4, with 14, 11 and 9 false alarms.

## What the evidence does not support

No causal claim; no claim of safety or health benefit (35 ug/m3 is a research threshold, not a safety limit); no claim of operational forecast quality; no generalisation beyond one week, eight cities and a weekend-only test. Uncertainty estimates should be treated cautiously because the primary inference uses only seven clusters (five for Q4).

## Recommendation

Do not change the advisory yet. Keep using the latest observed reading, and run a longer prospective evaluation (several weeks including weekdays) with predictions time-stamped when issued.
