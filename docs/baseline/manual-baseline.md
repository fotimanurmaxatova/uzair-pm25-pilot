# Manual baseline for value measures V1 to V3 (measure once, before assessed collection)

Task: look up the current PM2.5 and wind speed of 5 cities on a public website and type them
into a spreadsheet. Do this once, with a stopwatch, before 2 Nov 00:00. Do not tidy the
numbers afterwards; check each entry against the source.

| Item | Measured value |
|---|---|
| Date and time of measurement | |
| Website used (name, URL) | |
| V1: total time, 5 cities (seconds) | |
| V2: entries made / entries wrong or invalid | / |
| V3: manual steps to get descriptive statistics from the spreadsheet (list them) | |

Achieved (to be filled from the system, CP4): V1 median seconds from API response to record
visible on the dashboard; V2 seeded invalid inputs caught and real quarantine rate; V3 dashboard steps.

## Manual baseline methodology

- Method: Manual collection from Open-Meteo JSON pages.
- Cities: Tashkent, Samarkand, Bukhara, Andijan, Namangan.
- Data entries: 10 total (5 PM2.5 values and 5 wind speed values).
- PM2.5 source: Open-Meteo Air Quality API.
- Wind source: Open-Meteo Weather Forecast API.
- Wind speed unit: m/s.
- Collection method: Open each JSON URL in a browser and manually copy the required value.
- Timer starts: when the first JSON page is opened.
- Timer stops: after the tenth value is entered and Enter is pressed.
- V1: total manual collection time in seconds.
- V2: number of incorrect entries out of 10.
- V3: number of manual spreadsheet analysis steps.
- Rule: one measurement attempt; no repeating to obtain a better result.

## Manual Baseline Results

### Data source and method

Method A was used: manual collection from Open-Meteo JSON pages through a web browser.

- Air quality source: Open-Meteo Air Quality API (`pm2_5`, `cams_global`).
- Weather source: Open-Meteo Forecast API (`wind_speed_10m`).
- Wind speed unit: m/s.
- Cities: Tashkent, Samarkand, Bukhara, Andijan, Namangan.
- Total entries: 10 (5 PM2.5 values and 5 wind speed values).

### Collected data

| City | PM2.5 (µg/m³) | Wind speed (m/s) |
|---|---:|---:|
| Tashkent | 52.7 | 1.01 |
| Samarkand | 14.6 | 1.59 |
| Bukhara | 10.4 | 0.38 |
| Andijan | 44.0 | 1.68 |
| Namangan | 38.9 | 2.70 |

PM2.5 API timestamp: 2026-11-01 16:00  
Wind API timestamp: 2026-11-01 16:30

### V1 — Manual collection time

- Recorded time: 87.14 seconds.
- Method: browser-based manual collection and spreadsheet entry.

### V2 — Entry errors

- Reported incorrect entries: 9/10.
- This count should be interpreted as the user's reported error count and retained with the original entry record.

### V3 — Spreadsheet analysis steps

Two columns were analysed: PM2.5 and wind speed.

Five statistics were calculated for each column:
- Mean
- Median
- Standard deviation
- Minimum
- Maximum

Each calculation involved three actions:
1. Select the data range.
2. Enter the formula.
3. Press Enter.

Total: 5 × 2 × 3 = 30 manual steps.

### Limitations

The baseline measures manual workflow effort (time, entry errors, and analysis steps), not air-quality or weather accuracy.
Open-Meteo API values are model-based data and are not direct measurements from local ground sensors. The preparation attempt was 
not timed; V1 records the subsequent timed attempt. The same Open-Meteo source was used for both variables, 
making source verification easier but representing a conservative manual-workflow comparison.
