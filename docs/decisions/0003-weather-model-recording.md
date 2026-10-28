# 0003: Recording the weather model

Status: Accepted (2026-10-28)
Related: Issue #1, #5; decisions 0001 and 0002; Module Leader feedback

## Context
The approval feedback asks to record each source's valid timestamp, units
and model/domain. Air quality stored `aq_domain`, but the weather model was
not recorded anywhere.

## Decision
- The weather request sets `models=best_match` explicitly.
- Migration 0003 adds `observations.weather_model` (TEXT, NOT NULL, default
  `best_match`); the collector stores the requested model with every row.
- Rows stored before migration 0003 (development runs, is_pilot=1) were
  requested without the parameter; Open-Meteo's default is best_match, so
  they receive that value.
- This change is made before assessed collection starts (2 Nov 2026). Any
  later change to collector code or schema needs a written note to the
  Module Leader and a new decision record.

## Consequences
- Source, unit, valid time and model/domain are now recorded for both
  endpoints.
- `best_match` is a model selection rule, not one fixed model; the exact
  underlying model per location is not stored (documented limitation).