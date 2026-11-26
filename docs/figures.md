
# Figures and visualisation notes

## Data sources

Weather data are provided by Open-Meteo. Air-quality variables are sourced
from CAMS Global through the Open-Meteo Air Quality API.

Weather data by Open-Meteo.com; air quality from CAMS Global via the Open-Meteo
Air Quality API; derived values are labelled derived.

## Important interpretation note

PM2.5 values are modelled grid-cell estimates from CAMS Global, not direct
measurements from ground-based monitoring stations. Charts must therefore be
interpreted as model-based estimates rather than station observations.

## Original exploratory charts

The original six exploratory charts are stored in
`results/eda/full/`. Their manifest is `eda_manifest.json`.

The original chart files are preserved unchanged. Their SHA-256 values were
recorded and verified before post-test chart generation.

## Post-test annotated charts

Post-test annotated copies are stored in `results/post_test/eda/`.

Required label:

> post-test annotated copies; original charts in results/eda/full unchanged

The post-test set contains seven charts:

1. `01_pm25_time_series.png` — native three-hourly modelled PM2.5 observations
   over the assessed week by city.
2. `02_pm25_by_city.png` — distribution of native three-hourly modelled PM2.5
   values across cities.
3. `03_diurnal_profile.png` — mean modelled PM2.5 by local hour.
4. `04_pm25_vs_wind.png` — wind speed against modelled PM2.5 for native rows
   with both fields present.
5. `05_pm25_vs_humidity.png` — relative humidity against modelled PM2.5 for
   native rows with both fields present.
6. `06_coverage_by_city_day.png` — collected-row counts by city and local day.
7. `07_weather_pollutant_missingness.png` — null counts for weather and
   pollutant variables across assessed rows.

Each chart includes its sample count (`n`), a one-sentence caption, the
source attribution line, and the required post-test label.

The seventh chart distinguishes the six weather fields from the four
pollutant fields. A zero null count indicates complete coverage for that
field in the assessed rows.

## Population and timing

The primary PM2.5 analysis uses native three-hourly observations. Native
observations are identified using the project's UTC valid-time rule.

The post-test charts are generated only after the first held-out test
evaluation has created its evaluation marker and the post-test guard passes.
The script checks the original EDA file hashes before and after generation.

## Reproducibility

Script: `tools/eda_post_test.py`

Manifest: `results/post_test/eda/eda_post_test_manifest.json`

The manifest records the post-test tag and commit, chart sample counts,
chart SHA-256 values, original EDA hashes, and missing-value counts.
