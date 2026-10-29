
# 0005 — City coordinates (reference table)

Status: Accepted (2026-10-29)  
Related: Issue #2, #5; migration `0002_seed_cities.sql`

## Context

The `cities` table holds approximate city-centre coordinates used only as
the location of each API request. They are a small reference table and do
not replace any collected data. The air-quality source (CAMS global) has
a ~0.4° grid (~45 km), so exact centre coordinates are not critical.

## Check

Seed values were compared on 2026-10-29 with coordinates from GeoNames
(https://www.geonames.org), one feature page per city. Tashkent: GeoNames ID
1512569 (https://www.geonames.org/1512569/tashkent.html).

| City | Seed (lat, lon) | Reference (lat, lon) | Approx. offset | GeoNames reference |
|---|---|---|---|---|
| Urgench | 41.5500, 60.6333 | 41.55177, 60.63143 | 0.3 km | https://www.geonames.org/1512473/urgench.html |
| Nukus | 42.4531, 59.6103 | 42.45861, 59.60576 | 0.7 km | https://www.geonames.org/601294/nukus.html |
| Fergana | 40.3864, 71.7864 | 40.38421, 71.78432 | 0.3 km | https://www.geonames.org/1514019/fergana.html |
| Namangan | 41.0011, 71.6726 | 40.99830, 71.67257 | 0.3 km | https://www.geonames.org/1513157/namangan.html |
| Andijan | 40.7821, 72.3442 | 40.78338, 72.35067 | 0.6 km | https://www.geonames.org/1514588/andijon.html |
| Bukhara | 39.7747, 64.4286 | 39.77026, 64.43069 | 0.5 km | https://www.geonames.org/1217662/bukhara.html |
| Samarkand | 39.6542, 66.9597 | 39.65456, 66.96445 | 0.4 km | https://www.geonames.org/1216265/samarkand.html |
| Tashkent | 41.2995, 69.2401 | 41.26465, 69.21627 | 4.3 km | https://www.geonames.org/1512569/tashkent.html |

## Decision

Keep the seed values unchanged. All offsets are below 0.05° and are
small relative to the ~0.4° CAMS global grid.

For Tashkent (largest offset) the API cell returned for the reference point
(41.300003, 69.2) is identical to the cell in the saved sample, so the offset
does not change the air-quality values requested. 

The weather endpoint was not re-checked for the reference point; its grid is
finer, so a 4 km offset could in principle change the weather cell. This is
accepted for the pilot and noted as a limitation.

## Consequences

`migrations/0002_seed_cities.sql` must not be edited once assessed
collection starts on 2 November 2026. Any later change requires a new
migration and written approval from the Module Leader.
