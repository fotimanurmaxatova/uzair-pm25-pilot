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

- Open-Meteo states that data obtained through its APIs are provided under the Creative Commons Attribution 4.0 International (CC BY 4.0) licence. The applicable attribution must provide appropriate credit, link to the licence and indicate whether changes were made.
- The selected air-quality domain is `cams_global`. The CAMS Global atmospheric composition forecasts dataset is listed in the Copernicus Atmosphere Data Store (ADS) under CC BY 4.0, with DOI `10.24381/04a0b097`.
- Open-Meteo is the API provider and CAMS Global is the underlying air-quality forecast source. These roles must be distinguished in project documentation and outputs.
- The weather endpoint requests `models=best_match`. This is an automatic model-selection mechanism rather than one fixed weather model. According to the Open-Meteo documentation, its global model backbone includes DWD ICON, NOAA GFS and ECMWF IFS. Additional regional models may be selected where applicable.
- The project will retain the requested model setting and available source/provenance metadata. It will not claim that one specific weather model generated every observation unless this is confirmed by the available source metadata.
- Derived or transformed values, including analytical features and model outputs, will be identified as derived from the source data. Any modifications will be disclosed where applicable.

### 4. Attribution in project outputs

The attribution requirements were reviewed against the official Open-Meteo and Copernicus documentation on 10 November 2026.

**Weather data**

Weather forecasts obtained through Open-Meteo will be credited to Open-Meteo. The recommended attribution text is:

"Weather data by Open-Meteo.com"

The attribution will link to:
- https://open-meteo.com/

The model-selection method and contributing weather-model providers will be documented by linking to:
- https://open-meteo.com/en/docs

The `best_match` setting must not be presented as one fixed weather model. The documented global model backbone includes DWD ICON, NOAA GFS and ECMWF IFS. The applicable model selection may vary depending on location and model coverage.

**Air-quality data**

The air-quality forecast uses the CAMS Global atmospheric composition forecasts dataset through the Open-Meteo Air Quality API.

The project attribution will identify both providers:

"Air-quality forecast data: Copernicus Atmosphere Monitoring Service (CAMS), CAMS Global atmospheric composition forecasts (DOI: 10.24381/04a0b097), accessed through the Open-Meteo Air Quality API."

The attribution will link to:
- Open-Meteo Air Quality API: https://open-meteo.com/en/docs/air-quality-api
- CAMS Global dataset: https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts
- CC BY 4.0 licence: https://creativecommons.org/licenses/by/4.0/

Any transformations or derived analytical outputs will be identified, and the attribution will not imply endorsement by Open-Meteo, CAMS or the weather-model providers.

The source attribution must be visible in the CP4 dashboard and included in the final report and relevant figures. A release checklist will verify the attribution before publication.

If the source documentation, selected model configuration or applicable licence conditions change, the attribution must be reviewed again before publication.

### 5. Privacy

The project will not intentionally collect personal data. API requests use predefined city-centre coordinates rather than individual users' locations.

According to the reviewed Open-Meteo terms, server logs may contain IP addresses and requested coordinates and are deleted after 90 days. This logging is performed by the API provider, not by the project's local collection process.

## Consequences

- The project must remain within the permitted scope of the free API service.
- Commercial use of the Open-Meteo API service requires a paid subscription under the provider's applicable terms. Any reuse or redistribution of data must separately comply with the relevant licence conditions.
- The dashboard deliverable (CP4) must include visible source attribution. This requirement will be verified through a test or release checklist.
- The planned hourly schedule and actual request counts must be checked before assessed data collection begins.
- If the API terms, licence conditions or source attribution requirements change, this decision record must be reviewed and updated before those changes affect the pilot.
