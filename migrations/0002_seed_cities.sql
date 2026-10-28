-- Reference table (enrichment only): approximate city-centre coordinates.
-- TODO: verify each value against a public gazetteer and cite it in docs/decisions.
INSERT INTO cities (name, latitude, longitude) VALUES
    ('Tashkent',  41.2995, 69.2401),
    ('Samarkand', 39.6542, 66.9597),
    ('Bukhara',   39.7747, 64.4286),
    ('Andijan',   40.7821, 72.3442),
    ('Namangan',  41.0011, 71.6726),
    ('Fergana',   40.3864, 71.7864),
    ('Nukus',     42.4531, 59.6103),
    ('Urgench',   41.5500, 60.6333);