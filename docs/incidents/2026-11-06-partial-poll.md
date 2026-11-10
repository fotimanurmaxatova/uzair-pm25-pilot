# Incident 2026-11-06: partial collection at 22:00 Asia/Tashkent

Status: recorded; no back-fill performed

## What happened

The scheduled poll at 2026-11-06 22:00 Asia/Tashkent
(2026-11-06T17:00Z) completed for 7 of the 8 cities.

The Tashkent weather request timed out, and the Tashkent
air-quality request encountered a DNS error. The other
seven cities were collected.

## Effect on the data

- One city did not receive a complete weather and air-quality
  observation for this poll.
- The poll is classified as partial, not complete.
- The affected scheduled time remains incomplete in the assessed
  dataset.
- The coverage report records 191 of 192 expected city-rows
  for 6 November.

## Decision

- No back-fill was performed.
- The incomplete time remains a gap.
- No missing observation was fabricated or reconstructed.
- The incident is retained in the collection audit trail.

## Limitations

This record reports the observed timeout and DNS error.
It does not infer their underlying causes.
