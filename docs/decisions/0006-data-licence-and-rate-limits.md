# 0006 — Data Licensing, Attribution and Rate Limits

**Status:** Accepted (2026-10-29)  
**Related:** Issues #1 and #5

## Context

The UzAir pilot uses the Open-Meteo Weather Forecast API and Air Quality API. The weather endpoint requests the `best_match` model, which may combine forecasts from different weather-model providers. The air-quality endpoint explicitly requests the `cams_global` domain.

The project is conducted as university coursework for educational and non-commercial purposes. The Open-Meteo terms of use were reviewed on 29 October 2026: https://open-meteo.com/en/terms.

## Decision

### 1. Permitted use

- The API will be used for the university coursework pilot, which is educational and non-commercial.
- The project will not display advertisements, charge users or offer a paid subscription.
- Any future commercial use of the Open-Meteo API service must be reviewed against the provider's applicable subscription terms before implementation.

### 2. API rate limits and request volume

The published free-API limits are 600 calls per minute, 5,000 per hour, fewer than 10,000 per day, and 300,000 per month.

The planned collection schedule is:

- **Requests per run:** 16 (8 cities × 2 endpoints), excluding retries.
- **Planned runs per day:** 24, provided the hourly schedule is configured and runs successfully.
- **Expected requests per day:** 384, excluding retries.
- **Expected requests over the seven-day pilot (2–8 November 2026):** 2,688, excluding retries.

The collector retries eligible network errors, HTTP 429 responses and HTTP 5xx responses, with exponential backoff. It allows up to three retries per request (`MAX_RETRIES = 3` in `src/uzair/collector.py`), with delays of 2, 4 and 8 seconds. Other HTTP 4xx responses are not retried.

In the worst case, each initial request can result in four total attempts. This gives a maximum of 64 attempts per run, 1,536 attempts per day and 10,752 attempts over seven days, assuming 24 runs each day and every request reaches its retry limit. This worst-case weekly total is approximately 3.6% of the published monthly limit. Actual request counts depend on the configured schedule and the failures encountered.

The CLI performs one collection cycle each time the `collect` command is invoked; it does not configure the hourly schedule itself. The external scheduler must therefore be configured and verified before assessed collection begins.

### 3. Licensing and data provenance

- Data obtained through the Open-Meteo APIs are subject to the applicable CC BY 4.0 licence conditions.
- Raw API response bodies are stored unchanged for provenance and audit purposes.
- Derived or aggregated values, including analytical features and model outputs, will be identified as derived from the source data in the dashboard and report, where applicable.
- The repository will retain source and provenance information that distinguishes Open-Meteo as the API provider from CAMS Global as the underlying air-quality forecast source.
- The weather data source associated with `best_match` will be documented using the applicable Open-Meteo model-source documentation.

### 4. Attribution in project outputs

Where collected data are displayed in the dashboard, report or report figures, the output will visibly acknowledge Open-Meteo and identify the underlying data sources.

The attribution will link to the [Open-Meteo documentation](https://open-meteo.com/en/docs), the [Open-Meteo Air Quality API documentation](https://open-meteo.com/en/docs/air-quality-api), and the [CAMS Global atmospheric-composition forecasts dataset](https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts).

The exact CAMS attribution wording and any additional attribution requirements for the weather models selected by `best_match` must be checked against the applicable source documentation before the CP4 dashboard and final report are published. The verification is tracked in Issue #5.

### 5. Privacy

The project will not intentionally collect personal data. API requests use predefined city-centre coordinates rather than individual users' locations.

According to the reviewed Open-Meteo terms, server logs may contain IP addresses and requested coordinates and are deleted after 90 days. This logging is performed by the API provider, not by the project's local collection process.

## Consequences

- The project must remain within the permitted scope of the free API service.
- Commercial use of the Open-Meteo API service requires a paid subscription under the provider's applicable terms. Any reuse or redistribution of data must separately comply with the relevant licence conditions.
- The dashboard deliverable (CP4) must include visible source attribution. This requirement will be verified through a test or release checklist.
- The planned hourly schedule and actual request counts must be checked before assessed data collection begins.
- If the API terms, licence conditions or source attribution requirements change, this decision record must be reviewed and updated before those changes affect the pilot.
